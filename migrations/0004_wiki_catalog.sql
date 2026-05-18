-- Wiki catalog and source-sync metadata.
-- Source of truth remains controlled systems such as Google Drive, SweetProcess,
-- and boonegraphics.net/internal-wiki. Retriever stores internal cards,
-- reviewed summaries, source links, and sync state.

CREATE TABLE IF NOT EXISTS retriever_core.wiki_sources (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_key VARCHAR(80) NOT NULL UNIQUE,
    source_type VARCHAR(40) NOT NULL,
    title VARCHAR(255) NOT NULL,
    root_url TEXT NULL,
    sync_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS retriever_core.wiki_documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NULL,
    source_document_id VARCHAR(255) NULL,
    slug VARCHAR(180) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    document_code VARCHAR(80) NULL,
    document_type VARCHAR(80) NOT NULL DEFAULT 'article',
    category VARCHAR(120) NOT NULL DEFAULT 'General',
    summary_status VARCHAR(32) NOT NULL DEFAULT 'draft',
    summary TEXT NULL,
    audience VARCHAR(80) NOT NULL DEFAULT 'employee',
    raw_source_visible_to VARCHAR(40) NOT NULL DEFAULT 'admin',
    source_url TEXT NULL,
    source_modified_at DATETIME NULL,
    source_checksum VARCHAR(128) NULL,
    last_indexed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_wiki_documents_source
      FOREIGN KEY (source_id) REFERENCES retriever_core.wiki_sources(id)
      ON DELETE SET NULL
);

CREATE INDEX idx_wiki_documents_category ON retriever_core.wiki_documents (category);
CREATE INDEX idx_wiki_documents_type ON retriever_core.wiki_documents (document_type);
CREATE INDEX idx_wiki_documents_code ON retriever_core.wiki_documents (document_code);
CREATE INDEX idx_wiki_documents_source_doc ON retriever_core.wiki_documents (source_document_id);

CREATE TABLE IF NOT EXISTS retriever_core.wiki_document_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    source_revision_id VARCHAR(255) NULL,
    source_modified_at DATETIME NULL,
    summary TEXT NULL,
    summary_status VARCHAR(32) NOT NULL DEFAULT 'draft',
    extracted_text_hash VARCHAR(128) NULL,
    indexed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_wiki_versions_document
      FOREIGN KEY (document_id) REFERENCES retriever_core.wiki_documents(id)
      ON DELETE CASCADE
);

CREATE INDEX idx_wiki_versions_document_created
  ON retriever_core.wiki_document_versions (document_id, created_at);

CREATE TABLE IF NOT EXISTS retriever_core.wiki_sections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    slug VARCHAR(180) NOT NULL,
    heading VARCHAR(255) NOT NULL,
    section_order INT NOT NULL DEFAULT 0,
    summary TEXT NULL,
    body_status VARCHAR(32) NOT NULL DEFAULT 'draft',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_wiki_sections_document
      FOREIGN KEY (document_id) REFERENCES retriever_core.wiki_documents(id)
      ON DELETE CASCADE,
    UNIQUE KEY uq_wiki_sections_document_slug (document_id, slug)
);

CREATE INDEX idx_wiki_sections_document_order
  ON retriever_core.wiki_sections (document_id, section_order);

CREATE TABLE IF NOT EXISTS retriever_core.wiki_links (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NULL,
    source_id BIGINT NULL,
    label VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    link_type VARCHAR(60) NOT NULL DEFAULT 'source',
    visible_to VARCHAR(40) NOT NULL DEFAULT 'employee',
    discovered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_wiki_links_document
      FOREIGN KEY (document_id) REFERENCES retriever_core.wiki_documents(id)
      ON DELETE CASCADE,
    CONSTRAINT fk_wiki_links_source
      FOREIGN KEY (source_id) REFERENCES retriever_core.wiki_sources(id)
      ON DELETE SET NULL
);

CREATE INDEX idx_wiki_links_document_type ON retriever_core.wiki_links (document_id, link_type);

CREATE TABLE IF NOT EXISTS retriever_core.wiki_sync_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME NULL,
    scanned_count INT NOT NULL DEFAULT 0,
    changed_count INT NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    CONSTRAINT fk_wiki_sync_runs_source
      FOREIGN KEY (source_id) REFERENCES retriever_core.wiki_sources(id)
      ON DELETE SET NULL
);

CREATE INDEX idx_wiki_sync_runs_source_started
  ON retriever_core.wiki_sync_runs (source_id, started_at);
