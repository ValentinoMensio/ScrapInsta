-- Limpia toda la base de datos EXCEPTO clients y client_limits.
-- Orden respetando FKs: job_tasks -> jobs, profile_analysis -> profiles.

SET FOREIGN_KEY_CHECKS = 0;

DELETE FROM job_tasks;
DELETE FROM jobs;
DELETE FROM messages_sent;
DELETE FROM profile_analysis;
DELETE FROM followings;
DELETE FROM profiles;

SET FOREIGN_KEY_CHECKS = 1;
