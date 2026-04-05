-- PostgreSQL initialization script
-- Enables PostGIS and other extensions

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable crypto functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable trigram for search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enable unaccent for search
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Set default timezone
SET timezone = 'UTC';
