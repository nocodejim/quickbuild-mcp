-- QuickBuild 14 Database Creation Script
-- Creates the main quickbuild database with proper configuration
-- Executed during container initialization

USE master;
GO

-- Check if database already exists
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'quickbuild')
BEGIN
    PRINT 'Creating quickbuild database...'
    
    -- Create the quickbuild database
    CREATE DATABASE quickbuild
    COLLATE SQL_Latin1_General_CP1_CI_AS;
    
    PRINT 'quickbuild database created successfully.'
END
ELSE
BEGIN
    PRINT 'quickbuild database already exists.'
END
GO

-- Configure database settings for optimal QuickBuild performance
USE quickbuild;
GO

-- Set database options for better performance and compatibility
ALTER DATABASE quickbuild SET RECOVERY SIMPLE;
ALTER DATABASE quickbuild SET AUTO_CLOSE OFF;
ALTER DATABASE quickbuild SET AUTO_SHRINK OFF;
ALTER DATABASE quickbuild SET AUTO_CREATE_STATISTICS ON;
ALTER DATABASE quickbuild SET AUTO_UPDATE_STATISTICS ON;

PRINT 'Database configuration completed.'
GO