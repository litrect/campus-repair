-- 校园线上报修与后勤服务系统 A2 数据库基线
-- A2 修订稿 0.2；MySQL 8.0.16+；仅在空库执行，不是已有数据库迁移脚本。
-- 所有应用连接均须执行 SET time_zone='+08:00'；DATETIME 按北京时间存储。
SET time_zone = '+08:00';
CREATE DATABASE IF NOT EXISTS campus_repair
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE campus_repair;

CREATE TABLE `user` (
  id BIGINT NOT NULL AUTO_INCREMENT,
  username VARCHAR(50) NOT NULL,
  password VARCHAR(255) NOT NULL COMMENT '密码哈希，预留算法升级空间',
  real_name VARCHAR(50) NOT NULL,
  role VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  phone VARCHAR(20) NULL,
  skill VARCHAR(100) NULL COMMENT '维修工技能标签，逗号分隔；仅课程项目使用',
  is_active TINYINT NOT NULL DEFAULT 1,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_username (username),
  CONSTRAINT ck_user_role CHECK (role IN ('STUDENT','WORKER','ADMIN')),
  CONSTRAINT ck_user_active CHECK (is_active IN (0,1))
) ENGINE=InnoDB COMMENT='用户';

CREATE TABLE repair_order (
  id BIGINT NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(32) NOT NULL COMMENT '应用层生成的唯一工单号',
  student_id BIGINT NOT NULL,
  worker_id BIGINT NULL,
  request_token VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '客户端单次提交的幂等键',
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '标准化创建请求的 SHA256 摘要',
  category VARCHAR(20) NOT NULL,
  location VARCHAR(100) NOT NULL,
  description VARCHAR(500) NOT NULL,
  image_url VARCHAR(255) NULL,
  urgency VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'NORMAL',
  status VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'CREATED',
  repair_record VARCHAR(500) NULL COMMENT '维修工提交的最新维修记录',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  assign_time DATETIME NULL,
  accept_time DATETIME NULL,
  finish_time DATETIME NULL COMMENT '本轮完成时间；驳回时清空，历史时间保留在日志',
  deadline DATETIME NULL COMMENT '按待确认的 SLA 规则设定',
  is_overtime TINYINT NOT NULL DEFAULT 0,
  close_time DATETIME NULL,
  version INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_order_no (order_no),
  UNIQUE KEY uk_student_request (student_id, request_token),
  KEY idx_order_student_time (student_id, create_time),
  KEY idx_order_worker_status (worker_id, status),
  KEY idx_order_status_time (status, create_time),
  KEY idx_order_deadline (is_overtime, deadline),
  CONSTRAINT fk_order_student FOREIGN KEY (student_id) REFERENCES `user` (id) ON DELETE RESTRICT,
  CONSTRAINT fk_order_worker FOREIGN KEY (worker_id) REFERENCES `user` (id) ON DELETE RESTRICT,
  CONSTRAINT ck_order_urgency CHECK (urgency IN ('HIGH','NORMAL','LOW')),
  CONSTRAINT ck_order_status CHECK (status IN ('CREATED','ASSIGNED','PROCESSING','DONE','CLOSED','CANCELLED')),
  CONSTRAINT ck_order_overtime CHECK (is_overtime IN (0,1)),
  CONSTRAINT ck_order_version CHECK (version >= 0),
  CONSTRAINT ck_order_worker CHECK (
    (status = 'CREATED' AND worker_id IS NULL) OR
    (status IN ('ASSIGNED','PROCESSING','DONE','CLOSED') AND worker_id IS NOT NULL) OR
    status = 'CANCELLED'),
  CONSTRAINT ck_order_finish CHECK (
    (status IN ('DONE','CLOSED') AND finish_time IS NOT NULL AND repair_record IS NOT NULL AND CHAR_LENGTH(TRIM(repair_record)) > 0) OR
    (status NOT IN ('DONE','CLOSED') AND finish_time IS NULL)),
  CONSTRAINT ck_order_close CHECK (
    (status = 'CLOSED' AND close_time IS NOT NULL) OR
    (status <> 'CLOSED' AND close_time IS NULL)),
  CONSTRAINT ck_order_text CHECK (CHAR_LENGTH(TRIM(location)) > 0 AND CHAR_LENGTH(TRIM(description)) > 0 AND CHAR_LENGTH(TRIM(category)) > 0)
) ENGINE=InnoDB COMMENT='报修工单';

CREATE TABLE order_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  event_type VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  from_status VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '创建事件为空',
  to_status VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  order_version INT NOT NULL COMMENT '本次操作后工单版本；创建为0',
  operator_id BIGINT NULL COMMENT '仅 OVERTIME 系统事件为空',
  from_worker_id BIGINT NULL COMMENT '改派前维修工',
  to_worker_id BIGINT NULL COMMENT '派单或改派后维修工',
  remark VARCHAR(500) NULL COMMENT '完成时保存维修记录，驳回时保存原因',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_log_order_version (order_id, order_version),
  KEY idx_log_order_time (order_id, create_time, id),
  KEY idx_log_operator (operator_id),
  CONSTRAINT fk_log_order FOREIGN KEY (order_id) REFERENCES repair_order (id) ON DELETE RESTRICT,
  CONSTRAINT fk_log_operator FOREIGN KEY (operator_id) REFERENCES `user` (id) ON DELETE RESTRICT,
  CONSTRAINT fk_log_from_worker FOREIGN KEY (from_worker_id) REFERENCES `user` (id) ON DELETE RESTRICT,
  CONSTRAINT fk_log_to_worker FOREIGN KEY (to_worker_id) REFERENCES `user` (id) ON DELETE RESTRICT,
  CONSTRAINT ck_log_version CHECK (order_version >= 0),
  CONSTRAINT ck_log_actor CHECK ((event_type = 'OVERTIME' AND operator_id IS NULL) OR (event_type <> 'OVERTIME' AND operator_id IS NOT NULL)),
  CONSTRAINT ck_log_workers CHECK (
    (event_type = 'ASSIGN' AND from_worker_id IS NULL AND to_worker_id IS NOT NULL) OR
    (event_type = 'REASSIGN' AND from_worker_id IS NOT NULL AND to_worker_id IS NOT NULL AND from_worker_id <> to_worker_id) OR
    event_type NOT IN ('ASSIGN','REASSIGN')),
  CONSTRAINT ck_log_transition CHECK (
    (event_type = 'CREATE' AND from_status IS NULL AND to_status = 'CREATED') OR
    (from_status IS NOT NULL AND (
      (event_type = 'ASSIGN' AND from_status = 'CREATED' AND to_status = 'ASSIGNED') OR
      (event_type = 'REASSIGN' AND from_status = 'ASSIGNED' AND to_status = 'ASSIGNED') OR
      (event_type = 'ACCEPT' AND from_status = 'ASSIGNED' AND to_status = 'PROCESSING') OR
      (event_type = 'FINISH' AND from_status = 'PROCESSING' AND to_status = 'DONE') OR
      (event_type = 'CONFIRM' AND from_status = 'DONE' AND to_status = 'CLOSED') OR
      (event_type = 'REJECT' AND from_status = 'DONE' AND to_status = 'PROCESSING') OR
      (event_type = 'CANCEL' AND from_status IN ('CREATED','ASSIGNED') AND to_status = 'CANCELLED') OR
      (event_type = 'OVERTIME' AND from_status = to_status AND from_status IN ('CREATED','ASSIGNED','PROCESSING','DONE','CLOSED','CANCELLED'))
    )))
) ENGINE=InnoDB COMMENT='工单操作流水';

CREATE TABLE evaluation (
  id BIGINT NOT NULL AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  score TINYINT NOT NULL,
  content VARCHAR(300) NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_evaluation_order (order_id),
  CONSTRAINT fk_evaluation_order FOREIGN KEY (order_id) REFERENCES repair_order (id) ON DELETE RESTRICT,
  CONSTRAINT ck_evaluation_score CHECK (score BETWEEN 1 AND 5)
) ENGINE=InnoDB COMMENT='工单评价';
