-- RFC-005 需求三: Skill 新增 summary 摘要字段
-- MySQL 8.0 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS（MariaDB 语法）
-- 使用存储过程实现幂等迁移

DELIMITER //
DROP PROCEDURE IF EXISTS add_skill_summary_column //
CREATE PROCEDURE add_skill_summary_column()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'skill_store'
          AND COLUMN_NAME = 'summary'
    ) THEN
        ALTER TABLE skill_store
            ADD COLUMN summary TEXT COMMENT 'Skill 摘要, 30-80字, LLM生成' AFTER name;
    END IF;
END //
DELIMITER ;

CALL add_skill_summary_column();
DROP PROCEDURE IF EXISTS add_skill_summary_column;
