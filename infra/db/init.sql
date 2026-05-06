-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

-- Photos table (core entity)
CREATE TABLE IF NOT EXISTS photos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    s3_key VARCHAR(1024) NOT NULL,
    filename VARCHAR(512),
    mime_type VARCHAR(64),
    file_size_bytes BIGINT,
    width INTEGER,
    height INTEGER,
    taken_at TIMESTAMPTZ,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    caption TEXT,
    exif_data JSONB,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_photos_tenant_user ON photos(tenant_id, user_id);
CREATE INDEX idx_photos_status ON photos(status);
CREATE INDEX idx_photos_taken_at ON photos(taken_at);

-- Photo embeddings (pgvector)
CREATE TABLE IF NOT EXISTS photo_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    photo_id UUID NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    embedding VECTOR(768),
    caption_embedding VECTOR(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON photo_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_photo_embeddings_tenant_user ON photo_embeddings(tenant_id, user_id);

-- Row-level security policies
ALTER TABLE photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE photo_embeddings ENABLE ROW LEVEL SECURITY;

-- Phase 1: Google Photos ingestion additions
ALTER TABLE photos ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'google_photos';
ALTER TABLE photos ADD COLUMN IF NOT EXISTS external_id VARCHAR(512);
CREATE UNIQUE INDEX IF NOT EXISTS idx_photos_external_id
    ON photos(tenant_id, user_id, external_id)
    WHERE external_id IS NOT NULL;

-- OAuth token storage (one row per user+provider)
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(64) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expiry TIMESTAMPTZ,
    scope TEXT,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user ON oauth_tokens(user_id, provider);
ALTER TABLE oauth_tokens ENABLE ROW LEVEL SECURITY;

-- Seed a default tenant for local development
INSERT INTO tenants (id, name) VALUES
    ('00000000-0000-0000-0000-000000000001', 'Local Development')
ON CONFLICT DO NOTHING;

INSERT INTO users (id, tenant_id, email, display_name) VALUES
    ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'dev@memorylane.local', 'Dev User')
ON CONFLICT DO NOTHING;
