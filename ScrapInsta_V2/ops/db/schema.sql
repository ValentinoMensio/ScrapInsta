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
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  -- 👇 El nombre debe ser 'payload_json' para coincidir con JobStoreSQL.add_task
  payload_json JSON NULL,
  status ENUM('queued','sent','ok','error') DEFAULT 'queued',
  -- Compat: algunos métodos usan 'error_msg'; mantenemos ambas columnas
  error TEXT NULL,
  error_msg TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  -- opcionalmente útiles si ya los usás:
  sent_at TIMESTAMP NULL DEFAULT NULL,
  finished_at TIMESTAMP NULL DEFAULT NULL,
  INDEX idx_job_tasks_account_status_created (account_id, status, created_at),
  UNIQUE KEY uk_task_id (task_id),
  UNIQUE KEY uk_job_username_account (job_id, username, account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Retención sugerida (purga de tasks finalizadas viejas):
-- DELETE FROM job_tasks WHERE status IN ('ok','error') AND finished_at < NOW() - INTERVAL 90 DAY;


-- =========================================================
-- Tabla: messages_sent (ledger)
-- =========================================================
CREATE TABLE messages_sent (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  client_username VARCHAR(191) NOT NULL,
  dest_username  VARCHAR(191) NOT NULL,
  job_id   VARCHAR(191) NULL,
  task_id  VARCHAR(191) NULL,
  last_sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_messages_sent_client_dest (client_username, dest_username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
