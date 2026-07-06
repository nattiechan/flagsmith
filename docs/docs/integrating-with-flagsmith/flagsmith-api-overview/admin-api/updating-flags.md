---
title: Updating Flags (Experimental)
sidebar_label: Updating Flags (Experimental)
sidebar_position: 3
---

These experimental endpoints let you update feature flag values and segment overrides via the Admin API. They're
purpose-built for automation and CI/CD — minimal payloads, no need to look up internal IDs, and they work the same
regardless of whether your environment has Feature Versioning enabled.

:::caution

These endpoints are experimental and may change without notice. They cannot be used when
[change requests](/administration-and-security/governance-and-compliance/change-requests) are enabled.

:::

We're evaluating two approaches for updating flags — **Option A** (one change per request) and **Option B** (everything
in one request). Each scenario below shows both. Try them and
[let us know which works better for you](https://github.com/Flagsmith/flagsmith/issues/6233).

**Common details:**

- Identify features by `name` or `id` (pick one, not both).
- All endpoints return **204 No Content** on success.
- On the update endpoints, everything apart from `feature` is optional — anything you omit keeps its current state.
- Values are passed as a `value` object with `type` and `value` (always a string):

| Type      | Example                                |
| --------- | -------------------------------------- |
| `string`  | `{"type": "string", "value": "hello"}` |
| `integer` | `{"type": "integer", "value": "42"}`   |
| `boolean` | `{"type": "boolean", "value": "true"}` |

---

## Toggle a flag on or off

The simplest case — flip a feature flag in an environment.

**Option A** —
[`POST /api/experiments/environments/{environment_key}/update-flag-v1/`](https://api.flagsmith.com/api/v1/docs/#/experimental/api_experiments_environments_update_flag_v1_create)

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "maintenance_mode"},
    "enabled": true,
    "value": {"type": "boolean", "value": "true"}
  }'
```

**Option B** —
[`POST /api/experiments/environments/{environment_key}/update-flag-v2/`](https://api.flagsmith.com/api/v1/docs/#/experimental/api_experiments_environments_update_flag_v2_create)

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v2/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "maintenance_mode"},
    "environment_default": {
      "enabled": true,
      "value": {"type": "boolean", "value": "true"}
    }
  }'
```

---

## Update a feature value

Change a feature's value — for example, setting a rate limit.

**Option A**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "api_rate_limit"},
    "enabled": true,
    "value": {"type": "integer", "value": "1000"}
  }'
```

**Option B**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v2/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "api_rate_limit"},
    "environment_default": {
      "enabled": true,
      "value": {"type": "integer", "value": "1000"}
    }
  }'
```

---

## Manage multivariate options

Distribute a feature across weighted variations — for example, an A/B/n test on `button_colour`. The
`multivariate_options` array on the environment default is the feature's **full list of options**: entries without an
`id` create new options, entries with an `id` update existing ones, and any option left out of the list is deleted.
Sending an empty list removes all options.

Percentage allocations apply to the target environment only and must total 100 or less; the remainder falls through to
the control `value`. Below, 50% of identities get blue, 30% get green, and the remaining 20% fall through to the control
`#cccccc`.

**Option A**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "button_colour"},
    "enabled": true,
    "value": {"type": "string", "value": "#cccccc"},
    "multivariate_options": [
      {"percentage_allocation": 50, "value": {"type": "string", "value": "#0000ff"}},
      {"percentage_allocation": 30, "value": {"type": "string", "value": "#00ff00"}}
    ]
  }'
```

**Option B**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v2/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "button_colour"},
    "environment_default": {
      "enabled": true,
      "value": {"type": "string", "value": "#cccccc"},
      "multivariate_options": [
        {"percentage_allocation": 50, "value": {"type": "string", "value": "#0000ff"}},
        {"percentage_allocation": 30, "value": {"type": "string", "value": "#00ff00"}}
      ]
    }
  }'
```

To retrieve option `id`s, list them via
[`GET /api/v1/projects/{project_id}/features/{feature_id}/mv-options/`](https://api.flagsmith.com/api/v1/docs/#/projects/projects_features_mv_options_list).

:::caution

Option values are shared by all environments — updating an option's `value` (or deleting an option) affects every
environment of the project, while percentage allocations only change in the environment you target.

:::

### Adjust allocations for a segment override

Segment overrides can re-weight existing options, but not create, delete, or change their values. Reference options by
`id` and pass only `percentage_allocation`:

**Option A**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "button_colour"},
    "segment": {"id": 456},
    "multivariate_options": [
      {"id": 11, "percentage_allocation": 80}
    ]
  }'
```

**Option B**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v2/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "button_colour"},
    "segment_overrides": [
      {
        "segment_id": 456,
        "multivariate_options": [
          {"id": 11, "percentage_allocation": 80}
        ]
      }
    ]
  }'
```

---

## Roll out a feature to a segment

Enable a feature for a specific segment (e.g. beta users) while keeping it off for everyone else.

**Option A**

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "new_checkout"},
    "segment": {"id": 456},
    "enabled": true,
    "value": {"type": "boolean", "value": "true"}
  }'
```

**Option B** — single request:

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v2/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "new_checkout"},
    "environment_default": {
      "enabled": false,
      "value": {"type": "boolean", "value": "false"}
    },
    "segment_overrides": [
      {
        "segment_id": 456,
        "enabled": true,
        "value": {"type": "boolean", "value": "true"}
      }
    ]
  }'
```

The `priority` field on segment overrides is optional. Omit it to add at the lowest priority. Priority `1` is highest.

---

## Configure multiple segment overrides

Set different values per segment — for example, pricing tiers.

**Option A** — one request per segment override plus one for the default:

```bash
# Default
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "pricing_tier"},
    "enabled": true,
    "value": {"type": "string", "value": "standard"}
  }'

# Enterprise segment (highest priority)
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "pricing_tier"},
    "segment": {"id": 101, "priority": 1},
    "enabled": true,
    "value": {"type": "string", "value": "enterprise"}
  }'

# Premium segment
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v1/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "pricing_tier"},
    "segment": {"id": 202, "priority": 2},
    "enabled": true,
    "value": {"type": "string", "value": "premium"}
  }'
```

**Option B** — single request:

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/update-flag-v2/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "pricing_tier"},
    "environment_default": {
      "enabled": true,
      "value": {"type": "string", "value": "standard"}
    },
    "segment_overrides": [
      {
        "segment_id": 101,
        "priority": 1,
        "enabled": true,
        "value": {"type": "string", "value": "enterprise"}
      },
      {
        "segment_id": 202,
        "priority": 2,
        "enabled": true,
        "value": {"type": "string", "value": "premium"}
      }
    ]
  }'
```

---

## Remove a segment override

A separate endpoint for removing a segment override from a feature:

[`POST /api/experiments/environments/{environment_key}/delete-segment-override/`](https://api.flagsmith.com/api/v1/docs/#/experimental/api_experiments_environments_delete_segment_override_create)

```bash
curl -X POST 'https://api.flagsmith.com/api/experiments/environments/{environment_key}/delete-segment-override/' \
  -H 'Authorization: Api-Key <your_token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "feature": {"name": "pricing_tier"},
    "segment": {"id": 202}
  }'
```

---

## Quick reference

| Aspect             | Details                                                                                                                   |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| Feature ID         | `name` or `id` — use one, not both                                                                                        |
| Value types        | `string`, `integer`, `boolean`                                                                                            |
| Segment priority   | Optional — omit to add at lowest priority; `1` is highest                                                                 |
| Multivariate       | `multivariate_options` replaces the full option list at the environment default; segment overrides re-weight by `id` only |
| Feature Versioning | Works the same whether enabled or not                                                                                     |
| Success response   | `204 No Content`                                                                                                          |
| Limitations        | Incompatible with change requests                                                                                         |
| Full API schema    | [Swagger Explorer](https://api.flagsmith.com/api/v1/docs/)                                                                |
