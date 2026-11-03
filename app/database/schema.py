"""Schema v1: valores observados normalizados, sem disponibilidade calculada."""

APPLICATION_ID = 0x454D504F  # EMPO: identifica o banco derivado deste projeto.
SCHEMA_VERSION = 1

# Cada comando é executado separadamente dentro da transação. executescript()
# faria commit implícito e quebraria a atomicidade da substituição do snapshot.
SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY CHECK (category_id > 0),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        description TEXT NOT NULL CHECK (length(trim(description)) > 0)
    ) STRICT""",
    """CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY CHECK (product_id > 0),
        price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        category_id INTEGER NOT NULL REFERENCES categories(category_id),
        description TEXT NOT NULL CHECK (length(trim(description)) > 0),
        stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
        status TEXT NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
        specs TEXT NOT NULL CHECK (
            CASE WHEN json_valid(specs) THEN json_type(specs) = 'object' ELSE 0 END
        ),
        created_at TEXT NOT NULL CHECK (length(created_at) = 10 AND date(created_at) IS created_at)
    ) STRICT""",
    """CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER PRIMARY KEY CHECK (customer_id > 0),
        name TEXT NOT NULL CHECK (length(trim(name)) > 0),
        phone TEXT NOT NULL CHECK (length(trim(phone)) > 0),
        email TEXT NOT NULL CHECK (length(trim(email)) > 0),
        city TEXT NOT NULL CHECK (length(trim(city)) > 0)
    ) STRICT""",
    """CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY CHECK (order_id > 0),
        customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
        order_date TEXT NOT NULL CHECK (length(order_date) = 10 AND date(order_date) IS order_date),
        status TEXT NOT NULL CHECK (
            status IN ('delivered', 'confirmed', 'pending', 'cancelled', 'shipped')
        ),
        total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
        payment_method TEXT NOT NULL CHECK (length(trim(payment_method)) > 0),
        tracking_code TEXT CHECK (tracking_code IS NULL OR length(trim(tracking_code)) > 0),
        estimated_delivery TEXT CHECK (
            estimated_delivery IS NULL OR (
                length(estimated_delivery) = 10 AND date(estimated_delivery) IS estimated_delivery
            )
        ),
        notes TEXT CHECK (notes IS NULL OR length(trim(notes)) > 0)
    ) STRICT""",
    """CREATE TABLE IF NOT EXISTS order_items (
        order_id INTEGER NOT NULL REFERENCES orders(order_id),
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        PRIMARY KEY (order_id, product_id)
    ) STRICT""",
    """CREATE TABLE IF NOT EXISTS promotions (
        promotion_id INTEGER PRIMARY KEY CHECK (promotion_id > 0),
        product_id INTEGER NOT NULL REFERENCES products(product_id),
        discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
        description TEXT NOT NULL CHECK (length(trim(description)) > 0),
        is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
    ) STRICT""",
    "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_promotions_product ON promotions(product_id)",
)
