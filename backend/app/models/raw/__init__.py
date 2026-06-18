"""RAW layer models - staging tables 1:1 with Shoper API responses + GA4."""
from .raw_orders import RawOrder
from .raw_order_items import RawOrderItem
from .raw_products import RawProduct
from .raw_customers import RawCustomer
from .raw_payments import RawPayment
from .raw_shipments import RawShipping
from .raw_categories import RawCategory
from .raw_product_groups import RawProductGroup
from .raw_discounts import RawDiscount
from .raw_statuses import RawStatus
from .raw_producers import RawProducer
from .raw_taxes import RawTax
from .raw_product_stocks import RawProductStock
from .raw_parcels import RawParcel
from .raw_user_groups import RawUserGroup
from .raw_currencies import RawCurrency
from .raw_subscribers import RawSubscriber

from .raw_ga4_traffic import RawGA4Traffic
from .raw_ga4_sources import RawGA4Source
from .raw_ga4_pages import RawGA4Page
from .raw_ga4_geo import RawGA4Geo
from .raw_ga4_devices import RawGA4Device
from .raw_ga4_funnel import RawGA4Funnel, RawGA4FunnelDevice, RawGA4CartProduct

__all__ = [
    "RawOrder",
    "RawOrderItem",
    "RawProduct",
    "RawCustomer",
    "RawPayment",
    "RawShipping",
    "RawCategory",
    "RawProductGroup",
    "RawDiscount",
    "RawStatus",
    "RawProducer",
    "RawTax",
    "RawProductStock",
    "RawParcel",
    "RawUserGroup",
    "RawCurrency",
    "RawSubscriber",
    "RawGA4Traffic",
    "RawGA4Source",
    "RawGA4Page",
    "RawGA4Geo",
    "RawGA4Device",
    "RawGA4Funnel",
    "RawGA4FunnelDevice",
    "RawGA4CartProduct",
]
