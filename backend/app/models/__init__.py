"""Models package - RAW (staging) and CORE (star schema) layers."""
# Store config (multi-store support)
from .store import Store

# RAW layer (staging - 1:1 with Shoper API)
from .raw import (
    RawOrder,
    RawOrderItem,
    RawProduct,
    RawCustomer,
    RawPayment,
    RawShipping,
    RawCategory,
    RawDiscount,
    RawStatus,
    RawProducer,
    RawTax,
    RawProductStock,
    RawParcel,
    RawUserGroup,
    RawCurrency,
    RawSubscriber,
    RawGA4Traffic,
    RawGA4Source,
    RawGA4Page,
    RawGA4Geo,
    RawGA4Device,
)

# CORE layer (star schema - analytical model)
from .core import (
    FactOrder,
    FactOrderItem,
    DimCustomer,
    DimProduct,
    DimCategory,
    DimDate,
)

# Legacy models (deprecated - will be removed after migration)
from .order import Order, OrderItem
from .product import Product, ProductSnapshot
from .customer import Customer
from .traffic import TrafficStats

__all__ = [
    # Store
    "Store",
    # RAW layer
    "RawOrder",
    "RawOrderItem",
    "RawProduct",
    "RawCustomer",
    "RawPayment",
    "RawShipping",
    "RawCategory",
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
    # CORE layer
    "FactOrder",
    "FactOrderItem",
    "DimCustomer",
    "DimProduct",
    "DimCategory",
    "DimDate",
    # Legacy (deprecated)
    "Order",
    "OrderItem",
    "Product",
    "ProductSnapshot",
    "Customer",
    "TrafficStats",
]
