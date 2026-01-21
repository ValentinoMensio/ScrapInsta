-- =========================
-- Clientes (Multi-Tenant)
-- =========================
CREATE TABLE IF NOT EXISTS clients (
  id VARCHAR(64) NOT NULL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) UNIQUE,
  api_key_hash VARCHAR(255) NOT NULL,
  status ENUM('active','suspended','deleted') NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  metadata JSON NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_clients_status ON clients(status);

CREATE TABLE IF NOT EXISTS client_limits (
  client_id VARCHAR(64) NOT NULL PRIMARY KEY,
  requests_per_minute INT NOT NULL DEFAULT 60,
  requests_per_hour INT NOT NULL DEFAULT 1000,
  requests_per_day INT NOT NULL DEFAULT 10000,
  messages_per_day INT NOT NULL DEFAULT 500,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- Perfiles analizados
-- =========================
CREATE TABLE IF NOT EXISTS profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    bio TEXT,
    followers INT UNSIGNED,
    followings INT UNSIGNED,
    posts INT UNSIGNED,
    is_verified BOOLEAN DEFAULT FALSE,
    privacy ENUM('public', 'private', 'unknown') DEFAULT 'unknown',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE INDEX ix_profiles_username ON profiles(username);
CREATE INDEX idx_profiles_updated_at ON profiles(updated_at);


-- =========================
-- Traza de análisis
-- =========================
CREATE TABLE IF NOT EXISTS profile_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    profile_id INT NOT NULL,
    source VARCHAR(64),
    rubro VARCHAR(128),
    engagement_score FLOAT,
    success_score FLOAT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_profile_analysis_profile_id ON profile_analysis(profile_id);
CREATE INDEX idx_profile_analysis_analyzed_at ON profile_analysis(analyzed_at DESC);


-- =========================
-- Seguimientos de perfiles
-- =========================
CREATE TABLE IF NOT EXISTS `followings` (
  `username_origin` VARCHAR(64) NOT NULL,
  `username_target` VARCHAR(64) NOT NULL,
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`username_origin`, `username_target`),
  KEY `ix_followings_origin` (`username_origin`),
  KEY `ix_followings_target` (`username_target`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_followings_created_at ON followings(created_at);


-- ============================================
-- Job Store (persistencia de Jobs y Tasks)
-- ============================================
CREATE TABLE IF NOT EXISTS jobs (
  id            VARCHAR(64)  NOT NULL PRIMARY KEY,
  kind          VARCHAR(64)  NOT NULL,
  priority      INT          NOT NULL,
  batch_size    INT          NOT NULL,
  extra_json    JSON         NULL,
  total_items   INT          NOT NULL,
  status        ENUM('pending','running','done','error') NOT NULL DEFAULT 'pending',
  client_id     VARCHAR(64)  NOT NULL,
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);
CREATE INDEX idx_jobs_status_updated ON jobs(status, updated_at);
CREATE INDEX idx_jobs_client_status ON jobs(client_id, status);
CREATE INDEX idx_jobs_client_created ON jobs(client_id, created_at);


-- =========================================================
-- Tabla: job_tasks
-- =========================================================
CREATE TABLE job_tasks (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  job_id VARCHAR(191) NOT NULL,
  task_id VARCHAR(191) NOT NULL,
  correlation_id VARCHAR(191) NULL,
  account_id VARCHAR(191) NULL,
  username VARCHAR(191) NULL,
  payload_json JSON NULL,
  status ENUM('queued','sent','ok','error') DEFAULT 'queued',
  error TEXT NULL,
  error_msg TEXT NULL,
  client_id VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  sent_at TIMESTAMP NULL DEFAULT NULL,
  finished_at TIMESTAMP NULL DEFAULT NULL,
  leased_at TIMESTAMP NULL DEFAULT NULL,
  lease_ttl INT DEFAULT 300,
  attempts INT NOT NULL DEFAULT 0,
  lease_expires_at TIMESTAMP NULL DEFAULT NULL,
  leased_by VARCHAR(128) NULL DEFAULT NULL,
  INDEX idx_job_tasks_account_status_created (account_id, status, created_at),
  INDEX idx_job_tasks_status_leased (status, leased_at),
  INDEX idx_job_tasks_status_lease_expires (status, lease_expires_at),
  UNIQUE KEY uk_task_id (task_id),
  UNIQUE KEY uk_job_username_account (job_id, username, account_id),
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_job_tasks_job_status ON job_tasks(job_id, status);
CREATE INDEX idx_job_tasks_job_task ON job_tasks(job_id, task_id);
CREATE INDEX idx_job_tasks_job_id ON job_tasks(job_id);
CREATE INDEX idx_job_tasks_status_created ON job_tasks(status, created_at);
CREATE INDEX idx_job_tasks_status_finished ON job_tasks(status, finished_at);
CREATE INDEX idx_job_tasks_client_status ON job_tasks(client_id, status);
CREATE INDEX idx_job_tasks_client_created ON job_tasks(client_id, created_at);


-- =========================================================
-- Tabla: messages_sent (ledger)
-- =========================================================
CREATE TABLE messages_sent (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  client_username VARCHAR(191) NOT NULL,
  client_id VARCHAR(64) NOT NULL,
  dest_username  VARCHAR(191) NOT NULL,
  job_id   VARCHAR(191) NULL,
  task_id  VARCHAR(191) NULL,
  last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_messages_sent_client_dest (client_username, dest_username),
  FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_messages_sent_dest ON messages_sent(dest_username);
CREATE INDEX idx_messages_sent_client ON messages_sent(client_username);
CREATE INDEX idx_messages_sent_last_sent ON messages_sent(last_sent_at);
CREATE INDEX idx_messages_sent_client_id ON messages_sent(client_id);
CREATE INDEX idx_messages_sent_client_id_dest ON messages_sent(client_id, dest_username);

-- =========================
-- Cliente por defecto
-- =========================
INSERT INTO clients (id, name, email, api_key_hash, status)
VALUES ('default', 'Default Client', NULL, '', 'active')
ON DUPLICATE KEY UPDATE id=id;
