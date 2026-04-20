# Tracker Roadmap (Backlog)

Status: agreed plan to implement in stages.

## Stage 1 - Critical (ASAP)
- Add `session_id` in tracker events (30-minute inactivity timeout).
- Extend `purchase` event payload with:
  - `order_id`
  - `value`
  - `currency`
  - `items[]` (`product_id`, `name`, `price`, `quantity`)
- Keep fallback heuristics only when explicit purchase data is unavailable.

## Stage 2 - Event Stability
- Move from text-based click heuristics to explicit data attributes (for example `data-trk="add_to_cart"`).
- Keep current text heuristics as temporary fallback during migration.
- Define stable event contract for key actions:
  - `add_to_cart`
  - `remove_from_cart`
  - `begin_checkout`
  - checkout step actions

## Stage 3 - Intent + Checkout Quality
- Add intent events:
  - `view_item_list`
  - `select_item`
  - `search`
  - `filter`
  - `sort`
- Add checkout quality events/fields:
  - `checkout_error` (step + message)
  - `payment_method`
  - `shipping_method`
- Add checkout timing analysis (time between steps).

## Stage 4 - Attribution + Engagement
- Add attribution fields:
  - `utm_source`
  - `utm_medium`
  - `utm_campaign`
- Add engagement signals:
  - `scroll_depth` (25/50/75/100)
  - `time_on_page`
- Optional technical context:
  - `browser`
  - `screen_size`

## Current Product Split (agreed)
- `Traffic` tab: GA4-focused metrics.
- `Cart` tab: tracker-focused funnel and cart diagnostics.

