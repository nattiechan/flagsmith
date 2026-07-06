"""https://docs.flagsmith.com/integrating-with-flagsmith/flagsmith-api-overview/admin-api/updating-flags"""

from collections.abc import Callable
from typing import Any, TypeAlias

import pytest
from rest_framework.test import APIClient

from environments.models import Environment
from features.models import FeatureState
from features.multivariate.models import MultivariateFeatureOption
from features.versioning.tasks import enable_v2_versioning

FeatureUpdatePayload: TypeAlias = dict[str, Any]


@pytest.fixture(params=["feature_versioning_v1", "feature_versioning_v2"])
def versioned_environment(
    request: pytest.FixtureRequest,
    environment: int,
) -> Environment:
    if request.param == "feature_versioning_v2":
        enable_v2_versioning(environment_id=environment)
    return Environment.objects.get(id=environment)  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature: {
                "feature": {"id": feature},
                "value": {"type": "string", "value": "control"},
                "multivariate_options": [
                    {
                        "percentage_allocation": 50,
                        "value": {"type": "string", "value": "half"},
                    },
                    {
                        "percentage_allocation": 10,
                        "value": {"type": "string", "value": "bit more"},
                    },
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature: {
                "feature": {"id": feature},
                "environment_default": {
                    "value": {"type": "string", "value": "control"},
                    "multivariate_options": [
                        {
                            "percentage_allocation": 50,
                            "value": {"type": "string", "value": "half"},
                        },
                        {
                            "percentage_allocation": 10,
                            "value": {"type": "string", "value": "bit more"},
                        },
                    ],
                },
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__new_multivariate_options__adds_environment_default_multivariate_options(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int], FeatureUpdatePayload],
) -> None:
    # Given / When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature),
        format="json",
    )

    # Then
    assert response.status_code == 204
    assert dict(
        FeatureState.objects.get_live_feature_states(
            environment=versioned_environment,
            feature_id=feature,
            feature_segment=None,
        )
        .get()
        .multivariate_feature_state_values.values_list(
            "multivariate_feature_option__string_value", "percentage_allocation"
        )
    ) == {"half": 50, "bit more": 10}


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature, option: {
                "feature": {"id": feature},
                "multivariate_options": [
                    {
                        "id": option,
                        "percentage_allocation": 25,
                        "value": {"type": "string", "value": "halfer"},
                    },
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature, option: {
                "feature": {"id": feature},
                "environment_default": {
                    "multivariate_options": [
                        {
                            "id": option,
                            "percentage_allocation": 25,
                            "value": {"type": "string", "value": "halfer"},
                        },
                    ],
                },
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__existing_multivariate_options__updates_environment_default_multivariate_options(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    mv_option_50_percent: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int, int], FeatureUpdatePayload],
) -> None:
    # Given / When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature, mv_option_50_percent),
        format="json",
    )

    # Then
    assert response.status_code == 204
    assert dict(
        FeatureState.objects.get_live_feature_states(
            environment=versioned_environment,
            feature_id=feature,
            feature_segment=None,
        )
        .get()
        .multivariate_feature_state_values.values_list(
            "multivariate_feature_option__string_value", "percentage_allocation"
        )
    ) == {"halfer": 25}


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature, segment, option: {
                "feature": {"id": feature},
                "segment": {"id": segment},
                "multivariate_options": [
                    {"id": option, "percentage_allocation": 80},
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature, segment, option: {
                "feature": {"id": feature},
                "segment_overrides": [
                    {
                        "segment_id": segment,
                        "multivariate_options": [
                            {"id": option, "percentage_allocation": 80},
                        ],
                    },
                ],
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__segment_override__updates_multivariate_percentage_allocations(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    mv_option_value: str,
    mv_option_50_percent: int,
    segment: int,
    segment_featurestate: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int, int, int], FeatureUpdatePayload],
) -> None:
    # Given / When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature, segment, mv_option_50_percent),
        format="json",
    )

    # Then
    assert response.status_code == 204
    live_feature_states = FeatureState.objects.get_live_feature_states(
        environment=versioned_environment,
        feature_id=feature,
    )
    assert dict(
        live_feature_states.get(
            feature_segment__segment_id=segment
        ).multivariate_feature_state_values.values_list(
            "multivariate_feature_option__string_value", "percentage_allocation"
        )
    ) == {mv_option_value: 80}
    assert dict(
        live_feature_states.get(
            feature_segment=None
        ).multivariate_feature_state_values.values_list(
            "multivariate_feature_option__string_value", "percentage_allocation"
        )
    ) == {mv_option_value: 50}


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature: {
                "feature": {"id": feature},
                "multivariate_options": [],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature: {
                "feature": {"id": feature},
                "environment_default": {"multivariate_options": []},
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__empty_multivariate_options__deletes_environment_default_multivariate_options(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    mv_option_50_percent: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int], FeatureUpdatePayload],
) -> None:
    # Given / When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature),
        format="json",
    )

    # Then
    assert response.status_code == 204
    assert not MultivariateFeatureOption.objects.filter(feature_id=feature).exists()


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature, option: {
                "feature": {"id": feature},
                "multivariate_options": [
                    {"id": option, "percentage_allocation": 40},
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature, option: {
                "feature": {"id": feature},
                "environment_default": {
                    "multivariate_options": [
                        {"id": option, "percentage_allocation": 40},
                    ],
                },
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__partial_multivariate_options__deletes_omitted_options(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    mv_option_value: str,
    mv_option_50_percent: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int, int], FeatureUpdatePayload],
) -> None:
    # Given
    omitted_option = MultivariateFeatureOption.objects.create(
        feature_id=feature,
        type="unicode",
        string_value="omitted",
        default_percentage_allocation=10,
    )

    # When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature, mv_option_50_percent),
        format="json",
    )

    # Then
    assert response.status_code == 204
    assert not MultivariateFeatureOption.objects.filter(id=omitted_option.id).exists()
    assert dict(
        FeatureState.objects.get_live_feature_states(
            environment=versioned_environment,
            feature_id=feature,
            feature_segment=None,
        )
        .get()
        .multivariate_feature_state_values.values_list(
            "multivariate_feature_option__string_value", "percentage_allocation"
        )
    ) == {mv_option_value: 40}


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature, option: {
                "feature": {"id": feature},
                "multivariate_options": [
                    {"id": option, "percentage_allocation": 25},
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature, option: {
                "feature": {"id": feature},
                "environment_default": {
                    "multivariate_options": [
                        {"id": option, "percentage_allocation": 25},
                    ],
                },
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__omitted_enabled_and_value__keeps_current_state(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    mv_option_50_percent: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int, int], FeatureUpdatePayload],
) -> None:
    # Given
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/update-flag-v1/",
        {
            "feature": {"id": feature},
            "enabled": True,
            "value": {"type": "string", "value": "current"},
        },
        format="json",
    )
    assert response.status_code == 204

    # When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature, mv_option_50_percent),
        format="json",
    )

    # Then
    assert response.status_code == 204
    feature_state = FeatureState.objects.get_live_feature_states(
        environment=versioned_environment,
        feature_id=feature,
        feature_segment=None,
    ).get()
    assert feature_state.enabled is True
    assert feature_state.feature_state_value.string_value == "current"


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature, option: {
                "feature": {"id": feature},
                "multivariate_options": [
                    {
                        "id": option,
                        "percentage_allocation": 25,
                        "value": {"type": "string", "value": "halfer"},
                    },
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature, option: {
                "feature": {"id": feature},
                "environment_default": {
                    "multivariate_options": [
                        {
                            "id": option,
                            "percentage_allocation": 25,
                            "value": {"type": "string", "value": "halfer"},
                        },
                    ],
                },
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__existing_multivariate_options__keeps_allocations_in_other_environments(
    admin_client: APIClient,
    project: int,
    environment_api_key: str,
    feature: int,
    mv_option_50_percent: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int, int], FeatureUpdatePayload],
) -> None:
    # Given
    response = admin_client.post(
        "/api/v1/environments/",
        {"name": "Other Environment", "project": project},
        format="json",
    )
    other_environment = response.json()["id"]

    # When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature, mv_option_50_percent),
        format="json",
    )

    # Then option values are shared across environments; allocations are not
    assert response.status_code == 204
    assert dict(
        FeatureState.objects.get_live_feature_states(
            environment=Environment.objects.get(id=other_environment),
            feature_id=feature,
            feature_segment=None,
        )
        .get()
        .multivariate_feature_state_values.values_list(
            "multivariate_feature_option__string_value", "percentage_allocation"
        )
    ) == {"halfer": 50}


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        pytest.param(
            "update-flag-v1",
            lambda feature: {
                "feature": {"id": feature},
                "multivariate_options": [
                    {
                        "percentage_allocation": 60,
                        "value": {"type": "string", "value": "more"},
                    },
                    {
                        "percentage_allocation": 50,
                        "value": {"type": "string", "value": "less"},
                    },
                ],
            },
            id="option_a",
        ),
        pytest.param(
            "update-flag-v2",
            lambda feature: {
                "feature": {"id": feature},
                "environment_default": {
                    "multivariate_options": [
                        {
                            "percentage_allocation": 60,
                            "value": {"type": "string", "value": "more"},
                        },
                        {
                            "percentage_allocation": 50,
                            "value": {"type": "string", "value": "less"},
                        },
                    ],
                },
            },
            id="option_b",
        ),
    ],
)
def test_update_flag__multivariate_percentage_allocations_exceeding_100__responds_400(
    admin_client: APIClient,
    environment_api_key: str,
    feature: int,
    versioned_environment: Environment,
    endpoint: str,
    payload: Callable[[int], FeatureUpdatePayload],
) -> None:
    # Given / When
    response = admin_client.post(
        f"/api/experiments/environments/{environment_api_key}/{endpoint}/",
        payload(feature),
        format="json",
    )

    # Then
    assert response.status_code == 400
    assert "multivariate_options" in response.json()
    assert not MultivariateFeatureOption.objects.filter(feature_id=feature).exists()
