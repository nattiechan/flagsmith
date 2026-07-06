from typing import Any, cast

from django.db import transaction
from rest_framework import serializers

from core.dataclasses import AuthorData
from environments.models import Environment
from features.models import Feature, FeatureState
from features.multivariate.models import MultivariateFeatureOption
from features.versioning.dataclasses import (
    FlagChangeSet,
    FlagChangeSetV2,
    MultivariateValueChangeSet,
    SegmentOverrideChangeSet,
)
from features.versioning.versioning_service import (
    delete_segment_override,
    update_flag,
    update_flag_v2,
)
from segments.models import Segment


class BaseFeatureUpdateSerializer(serializers.Serializer):  # type: ignore[type-arg]
    @property
    def environment(self) -> Environment:
        environment: Environment | None = self.context.get("environment")
        if not environment:
            raise serializers.ValidationError("Environment context is required")
        return environment

    def get_feature(self) -> Feature:
        feature_data = self.validated_data["feature"]
        try:
            feature: Feature = Feature.objects.get(
                project_id=self.environment.project_id, **feature_data
            )
            return feature
        except Feature.DoesNotExist:
            raise serializers.ValidationError(
                f"Feature '{feature_data}' not found in project"
            )

    def validate_segment_id(self, segment_id: int) -> None:
        if not Segment.objects.filter(
            id=segment_id, project_id=self.environment.project_id
        ).exists():
            raise serializers.ValidationError(
                f"Segment with id {segment_id} not found in project"
            )


class FeatureIdentifierSerializer(serializers.Serializer):  # type: ignore[type-arg]
    name = serializers.CharField(required=False, allow_blank=False)
    id = serializers.IntegerField(required=False)

    def validate(self, data: dict) -> dict:  # type: ignore[type-arg]
        has_name = "name" in data
        has_id = "id" in data
        if not has_name and not has_id:
            raise serializers.ValidationError(
                "Either 'name' or 'id' is required for feature identification"
            )
        if has_name and has_id:
            raise serializers.ValidationError("Provide either 'name' or 'id', not both")
        return data


class FeatureUpdateSegmentDataSerializer(serializers.Serializer):  # type: ignore[type-arg]
    id = serializers.IntegerField(required=True)
    priority = serializers.IntegerField(required=False, allow_null=True)


class FeatureValueSerializer(serializers.Serializer):  # type: ignore[type-arg]
    type = serializers.ChoiceField(
        choices=["integer", "string", "boolean"], required=True
    )
    value = serializers.CharField(required=True, allow_blank=True)

    def validate(self, data: dict) -> dict:  # type: ignore[type-arg]
        value_type = data["type"]
        string_val = data["value"]

        if value_type == "integer":
            try:
                int(string_val)
            except ValueError:
                raise serializers.ValidationError(
                    f"'{string_val}' is not a valid integer"
                )
        elif value_type == "boolean":
            if string_val.lower() not in ("true", "false"):
                raise serializers.ValidationError(
                    f"'{string_val}' is not a valid boolean (use 'true' or 'false')"
                )

        return data


class MultivariateOptionListSerializer(serializers.ListSerializer):  # type: ignore[type-arg]
    def update(
        self,
        instance: Feature,
        validated_data: list[dict[str, Any]],
    ) -> list[MultivariateFeatureOption]:
        """Reconcile the feature's multivariate options with an absolute list:
        create entries without an id, update entries by id, delete omitted options.
        """
        existing = {option.id: option for option in instance.multivariate_options.all()}
        options = []
        for option_data in validated_data:
            if option_id := option_data.get("id"):
                option = existing.pop(option_id)
            else:
                option = MultivariateFeatureOption(
                    feature=instance, default_percentage_allocation=0
                )
            if value_data := option_data.get("value"):
                option.set_value(value_data["value"], value_data["type"])
            option.save()
            options.append(option)
        for option in existing.values():
            option.delete()
        return options


class MultivariateOptionSerializer(serializers.Serializer):  # type: ignore[type-arg]
    id = serializers.IntegerField(required=False)
    percentage_allocation = serializers.FloatField(
        required=True, min_value=0, max_value=100
    )
    value = FeatureValueSerializer(required=False)

    class Meta:
        list_serializer_class = MultivariateOptionListSerializer


class SegmentMultivariateOptionSerializer(serializers.Serializer):  # type: ignore[type-arg]
    id = serializers.IntegerField(required=True)
    percentage_allocation = serializers.FloatField(
        required=True, min_value=0, max_value=100
    )

    def to_internal_value(self, data: dict) -> dict:  # type: ignore[type-arg]
        if "value" in data:
            raise serializers.ValidationError(
                "Multivariate option values can only be set at the environment "
                "default level"
            )
        return super().to_internal_value(data)  # type: ignore[no-any-return]


def validate_multivariate_options(
    feature: Feature | None,
    options: list[dict[str, Any]],
) -> None:
    if sum(option["percentage_allocation"] for option in options) > 100:
        raise serializers.ValidationError(
            {"multivariate_options": "Percentage allocations must not exceed 100"}
        )
    option_ids = [option["id"] for option in options if "id" in option]
    if len(option_ids) != len(set(option_ids)):
        raise serializers.ValidationError(
            {"multivariate_options": "Multivariate options must be unique"}
        )
    if feature is None or not option_ids:
        return
    valid = set(feature.multivariate_options.values_list("id", flat=True))
    if invalid := set(option_ids) - valid:
        raise serializers.ValidationError(
            {
                "multivariate_options": (
                    f"Multivariate options {sorted(invalid)} do not belong to "
                    "the feature"
                )
            }
        )


class UpdateFlagSerializer(BaseFeatureUpdateSerializer):
    feature = FeatureIdentifierSerializer(required=True)
    segment = FeatureUpdateSegmentDataSerializer(required=False)
    enabled = serializers.BooleanField(required=False)
    value = FeatureValueSerializer(required=False)
    multivariate_options = MultivariateOptionSerializer(many=True, required=False)

    def validate_segment(self, value: dict) -> dict:  # type: ignore[type-arg]
        if value and "id" in value:
            self.validate_segment_id(value["id"])
        return value

    def validate(self, data: dict) -> dict:  # type: ignore[type-arg]
        options = data.get("multivariate_options")
        if options is None:
            return data
        if data.get("segment") and any(
            "id" not in option or "value" in option for option in options
        ):
            raise serializers.ValidationError(
                {
                    "multivariate_options": (
                        "Segment overrides can only update percentage allocations "
                        "of existing multivariate options"
                    )
                }
            )
        feature = Feature.objects.filter(
            project_id=self.environment.project_id, **data["feature"]
        ).first()
        validate_multivariate_options(feature, options)
        return data

    @property
    def flag_change_set(self) -> FlagChangeSet:
        validated_data = self.validated_data
        value_data = validated_data.get("value")
        segment_data = validated_data.get("segment")

        return FlagChangeSet(
            author=AuthorData.from_request(self.context["request"]),
            enabled=validated_data.get("enabled"),
            feature_state_value=value_data["value"] if value_data else None,
            type_=value_data["type"] if value_data else None,
            segment_id=segment_data.get("id") if segment_data else None,
            segment_priority=segment_data.get("priority") if segment_data else None,
        )

    def save(self, **kwargs: object) -> FeatureState:
        with transaction.atomic():
            feature = self.get_feature()
            change_set = self.flag_change_set
            options_data = self.validated_data.get("multivariate_options")
            if options_data is not None:
                if change_set.segment_id is None:
                    options = cast(
                        MultivariateOptionListSerializer,
                        self.fields["multivariate_options"],
                    ).update(feature, options_data)
                    option_ids = [option.id for option in options]
                else:
                    option_ids = [option_data["id"] for option_data in options_data]
                change_set.multivariate_values = [
                    MultivariateValueChangeSet(
                        multivariate_feature_option_id=option_id,
                        percentage_allocation=option_data["percentage_allocation"],
                    )
                    for option_id, option_data in zip(
                        option_ids, options_data, strict=True
                    )
                ]
            return update_flag(self.environment, feature, change_set)


class EnvironmentDefaultSerializer(serializers.Serializer):  # type: ignore[type-arg]
    enabled = serializers.BooleanField(required=False)
    value = FeatureValueSerializer(required=False)
    multivariate_options = MultivariateOptionSerializer(many=True, required=False)


class MultivariateValueSerializer(serializers.Serializer):  # type: ignore[type-arg]
    multivariate_feature_option = serializers.IntegerField(required=True)
    percentage_allocation = serializers.FloatField(
        required=True, min_value=0, max_value=100
    )


class SegmentOverrideSerializer(serializers.Serializer):  # type: ignore[type-arg]
    segment_id = serializers.IntegerField(required=True)
    priority = serializers.IntegerField(required=False, allow_null=True)
    enabled = serializers.BooleanField(required=False)
    value = FeatureValueSerializer(required=False)
    multivariate_options = SegmentMultivariateOptionSerializer(
        many=True, required=False
    )


class UpdateFlagV2Serializer(BaseFeatureUpdateSerializer):
    feature = FeatureIdentifierSerializer(required=True)
    environment_default = EnvironmentDefaultSerializer(required=False)
    segment_overrides = SegmentOverrideSerializer(many=True, required=False)

    def validate_segment_overrides(
        self,
        value: list[dict],  # type: ignore[type-arg]
    ) -> list[dict]:  # type: ignore[type-arg]
        if not value:
            return value

        segment_ids = [override["segment_id"] for override in value]
        if len(segment_ids) != len(set(segment_ids)):
            raise serializers.ValidationError(
                "Duplicate segment_id values are not allowed"
            )

        # TODO: optimise this once out of experimentation
        for segment_id in segment_ids:
            self.validate_segment_id(segment_id)

        return value

    def validate(self, data: dict) -> dict:  # type: ignore[type-arg]
        env_default = data.get("environment_default") or {}
        options_by_holder = [
            env_default.get("multivariate_options"),
            *(
                override.get("multivariate_options")
                for override in data.get("segment_overrides", [])
            ),
        ]
        if all(options is None for options in options_by_holder):
            return data

        feature = Feature.objects.filter(
            project_id=self.environment.project_id, **data["feature"]
        ).first()
        for options in options_by_holder:
            if options is not None:
                validate_multivariate_options(feature, options)
        return data

    @property
    def change_set_v2(self) -> FlagChangeSetV2:
        validated_data = self.validated_data

        env_default = validated_data.get("environment_default") or {}
        env_value_data = env_default.get("value")

        segment_overrides_data = validated_data.get("segment_overrides", [])
        segment_overrides = []

        for override_data in segment_overrides_data:
            value_data = override_data.get("value")

            multivariate_data = override_data.get("multivariate_options")
            segment_override = SegmentOverrideChangeSet(
                segment_id=override_data["segment_id"],
                enabled=override_data.get("enabled"),
                feature_state_value=value_data["value"] if value_data else None,
                type_=value_data["type"] if value_data else None,
                priority=override_data.get("priority"),
                multivariate_values=[
                    MultivariateValueChangeSet(
                        multivariate_feature_option_id=option_data["id"],
                        percentage_allocation=option_data["percentage_allocation"],
                    )
                    for option_data in multivariate_data
                ]
                if multivariate_data
                else None,
            )
            segment_overrides.append(segment_override)

        return FlagChangeSetV2(
            author=AuthorData.from_request(self.context["request"]),
            environment_default_enabled=env_default.get("enabled"),
            environment_default_value=(
                env_value_data["value"] if env_value_data else None
            ),
            environment_default_type=env_value_data["type"] if env_value_data else None,
            segment_overrides=segment_overrides,
        )

    def save(self, **kwargs: object) -> None:
        with transaction.atomic():
            feature = self.get_feature()
            change_set = self.change_set_v2
            env_default = self.validated_data.get("environment_default") or {}
            options_data = env_default.get("multivariate_options")
            if options_data is not None:
                environment_default_field = cast(
                    EnvironmentDefaultSerializer, self.fields["environment_default"]
                )
                options = cast(
                    MultivariateOptionListSerializer,
                    environment_default_field.fields["multivariate_options"],
                ).update(feature, options_data)
                change_set.environment_default_multivariate_values = [
                    MultivariateValueChangeSet(
                        multivariate_feature_option_id=option.id,
                        percentage_allocation=option_data["percentage_allocation"],
                    )
                    for option, option_data in zip(options, options_data, strict=True)
                ]
            update_flag_v2(self.environment, feature, change_set)


class SegmentIdentifierSerializer(serializers.Serializer):  # type: ignore[type-arg]
    id = serializers.IntegerField(required=True)


class DeleteSegmentOverrideSerializer(BaseFeatureUpdateSerializer):
    feature = FeatureIdentifierSerializer(required=True)
    segment = SegmentIdentifierSerializer(required=True)

    def validate_segment(self, value: dict) -> dict:  # type: ignore[type-arg]
        if value and value.get("id"):
            self.validate_segment_id(value["id"])
        return value

    def save(self, **kwargs: object) -> None:
        feature = self.get_feature()
        segment_id = self.validated_data["segment"]["id"]
        author = AuthorData.from_request(self.context["request"])

        delete_segment_override(self.environment, feature, segment_id, author)
