# Database migrations
Plain SQL files applied in filename order and recorded in the `schema_migrations` table.
- Apply pending: `python manage.py migrate` (also runs automatically on every app start).
- Add a change: create `002_short_name.sql` (never edit an applied file). Example: `ALTER TABLE agents ADD COLUMN notes TEXT NOT NULL DEFAULT '';`
- Start over in development: `python manage.py reset` (deletes the DB!).
- Moving to PostgreSQL later: port the SQL (AUTOINCREMENT -> SERIAL/IDENTITY, TEXT dates -> timestamptz) and replace `app/db.py`.
