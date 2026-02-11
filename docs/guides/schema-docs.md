# Schema Documentation

The `DATABASE.md` file provides context about your database to the AI agent. The more detail you include, the better the agent will understand your data and generate accurate SQL queries.

## Why Schema Docs?

The AI agent needs to know:

- What **tables** exist and what they contain
- What **columns** are in each table and their types
- How tables are **related** (foreign keys)
- Any **business rules** or naming conventions
- **Example queries** that illustrate common patterns

Without this context, the agent may guess table/column names incorrectly or write suboptimal SQL.

---

## Quick Start

Run `tp init` to generate a template, then edit `DATABASE.md` in your project directory:

```bash
tp init
# Edit DATABASE.md with your actual schema
```

Point the client to it:

```python
import thinkingproducts as tp

# Option A: Auto-detected from ./DATABASE.md
client = tp.Client()

# Option B: Explicit path
client = tp.Client(schema_docs_path="./my_schema.md")

# Option C: Inline string
client = tp.Client(schema_docs="# Schema\n\n## Tables\n\n### users\n...")
```

---

## Recommended Format

````markdown
# Database Schema

## Database Information
- **Name:** myapp_production
- **Version:** PostgreSQL 15
- **Timezone:** UTC

## Conventions
- Primary keys: always `id` (integer or UUID)
- Foreign keys: format `{table}_id`
- Timestamps: `created_at`, `updated_at` (TIMESTAMPTZ)
- Soft deletes: `deleted_at` column (NULL = active)

## Tables

### users
Registered application users.

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | text | Full name |
| email | text | Unique email address |
| plan | text | Subscription plan: 'free', 'pro', 'enterprise' |
| created_at | timestamptz | Registration date |

### orders
Purchase orders placed by users.

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| user_id | integer | FK → users.id |
| total | numeric(10,2) | Order total in USD |
| status | text | 'pending', 'paid', 'shipped', 'delivered', 'cancelled' |
| created_at | timestamptz | Order date |

### order_items
Individual items within an order.

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| order_id | integer | FK → orders.id |
| product_id | integer | FK → products.id |
| quantity | integer | Units ordered |
| unit_price | numeric(10,2) | Price per unit at time of order |

### products
Product catalog.

| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | text | Product name |
| category | text | Product category |
| price | numeric(10,2) | Current retail price in USD |
| active | boolean | Whether the product is currently available |

## Relationships
- users.id → orders.user_id (one user has many orders)
- orders.id → order_items.order_id (one order has many items)
- products.id → order_items.product_id (one product in many order items)

## Business Rules
- Order totals should match the sum of (quantity × unit_price) for all items
- Only 'paid' and 'shipped' orders count as revenue
- Products with active=false should not appear in new orders

## Example Queries

**Top 10 customers by total spend:**
```sql
SELECT u.name, SUM(o.total) as total_spend
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.status IN ('paid', 'shipped', 'delivered')
GROUP BY u.name
ORDER BY total_spend DESC
LIMIT 10;
```
````

---

## Tips for Better Results

### 1. Be specific about column values

Instead of:

```markdown
| status | text | Order status |
```

Write:

```markdown
| status | text | 'pending', 'paid', 'shipped', 'delivered', 'cancelled' |
```

### 2. Document computed relationships

If certain queries require specific JOINs, show them:

```markdown
## Notes
- To get user names with order data, JOIN users ON users.id = orders.user_id
- Revenue = SUM(total) WHERE status IN ('paid', 'shipped', 'delivered')
```

### 3. Include example queries

Example queries teach the AI agent your preferred query patterns:

```markdown
## Example Queries

**Active users in the last 30 days:**
```sql
SELECT DISTINCT u.name
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.created_at >= CURRENT_DATE - INTERVAL '30 days';
```
```

### 4. Note any quirks

```markdown
## Caveats
- The `total` column in orders is stored in cents (divide by 100 for dollars)
- Dates before 2023 use a different timezone convention
- The `legacy_users` table is deprecated, use `users` instead
```

### 5. Keep it updated

When your schema changes, update `DATABASE.md` accordingly. The AI agent can only work with the information you provide.
