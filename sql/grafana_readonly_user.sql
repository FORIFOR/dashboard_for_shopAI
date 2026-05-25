-- Read-only PostgreSQL user for the Grafana "ShopAI PostgreSQL" datasource.
-- Run on the Backend VM against the shopai database. The password must match
-- SHOPAI_DASHBOARD_DB_PASSWORD in .env.
--
--   ! psql "postgresql://shopai@localhost:5432/shopai" -v pw="'<SHOPAI_DASHBOARD_DB_PASSWORD>'" -f sql/grafana_readonly_user.sql
--
-- (Or paste the statements into psql, replacing the password literal.)

-- Use \set pw '...' or replace :'pw' below with a quoted literal if not using -v.
CREATE USER shopai_dashboard WITH PASSWORD :'pw';

GRANT CONNECT ON DATABASE shopai TO shopai_dashboard;
GRANT USAGE ON SCHEMA public TO shopai_dashboard;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO shopai_dashboard;

-- Future tables created in public are also readable by the dashboard user.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO shopai_dashboard;

-- Belt and braces: never allow writes.
ALTER USER shopai_dashboard SET default_transaction_read_only = on;
