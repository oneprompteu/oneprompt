# Database Schema

Describe your database tables here. This helps the AI agent
understand your data structure and write better SQL queries.

## Tables

### users
| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | text | User name |
| email | text | User email |
| created_at | timestamp | Registration date |

### orders
| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| user_id | integer | Foreign key to users |
| total | numeric | Order total |
| created_at | timestamp | Order date |

## Relationships
- users.id → orders.user_id (one-to-many)
