# SQL guardrail

Agents may write SQL, but a script that changes state in production (ALTER, UPDATE, DELETE, INSERT, MERGE) follows one fixed format and is never run by an agent. The owner runs it, after the SQL reviewer approves it.

## Rules

1. One script per database or connection, with numbered sections and `PRINT` plus `GO` between them. The script is run whole, never "just block 3".
2. Self-contained: the script discovers its own parameters (for example the tenant code) from the database instead of asking the operator to edit values.
3. The top of the script prints the server and the database (`@@SERVERNAME`, `DB_NAME()`), so the output proves where it ran.
4. Baseline before: a SELECT that shows the rows and counts the change will touch.
5. Simulation: the change written as a SELECT that returns the old and the new value side by side, so the delta can be checked before anything is written.
6. Apply switch: the change itself sits behind `@APPLY`, which is `0` by default. With `@APPLY = 0` the script is a dry run and writes nothing. The write runs inside a transaction and checks the affected row count.
7. Rollback: the rows are saved to a backup table before the change, and a rollback block, behind its own switch (`@RESTORE`, also `0` by default), restores them.
8. Baseline after: the same query as the baseline before, so before and after can be compared line by line.
9. SQL reviewer: every state-changing script goes through the `sql-reviewer` agent (or a human reviewer). A missing section or a reviewer rejection blocks delivery.
10. Diagnosis in production is sampled (`TOP`) and read-uncommitted (`WITH (NOLOCK)` or `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`), never a full scan of a large table.

## Skeleton (T-SQL)

Table and column names are placeholders. Variables do not survive a `GO`, so each batch declares or re-derives what it needs; section 0 only prints the discovered tenant so the output records it.

```sql
SET NOCOUNT ON;
PRINT '=== 0 where am I ===';
PRINT 'server: ' + @@SERVERNAME;
PRINT 'database: ' + DB_NAME();
DECLARE @TENANT varchar(20) = (SELECT TOP 1 TenantCode FROM dbo.TenantConfig WITH (NOLOCK));
PRINT 'tenant: ' + ISNULL(@TENANT, '(not found)');
GO

PRINT '=== 1 baseline before ===';
SELECT TOP 100 t.Id, t.Status, t.UpdatedAt
FROM dbo.TargetTable t WITH (NOLOCK)
WHERE t.Status = 'PENDING' AND t.UpdatedAt < '2026-01-01';
SELECT COUNT(*) AS rows_to_change
FROM dbo.TargetTable t WITH (NOLOCK)
WHERE t.Status = 'PENDING' AND t.UpdatedAt < '2026-01-01';
GO

PRINT '=== 2 simulation as SELECT ===';
SELECT TOP 100 t.Id, t.Status AS old_status, 'CANCELLED' AS new_status
FROM dbo.TargetTable t WITH (NOLOCK)
WHERE t.Status = 'PENDING' AND t.UpdatedAt < '2026-01-01';
GO

PRINT '=== 3 apply (off by default) ===';
DECLARE @APPLY bit = 0;
DECLARE @EXPECTED int = (SELECT COUNT(*) FROM dbo.TargetTable
                         WHERE Status = 'PENDING' AND UpdatedAt < '2026-01-01');
IF @APPLY = 0
BEGIN
    PRINT 'dry run: nothing written, rows that would change: ' + CAST(@EXPECTED AS varchar(20));
END
ELSE
BEGIN
    BEGIN TRY
        BEGIN TRAN;
        SELECT t.Id, t.Status, t.UpdatedAt
        INTO dbo.TargetTable_backup_20260101
        FROM dbo.TargetTable t
        WHERE t.Status = 'PENDING' AND t.UpdatedAt < '2026-01-01';

        UPDATE t SET t.Status = 'CANCELLED'
        FROM dbo.TargetTable t
        JOIN dbo.TargetTable_backup_20260101 b ON b.Id = t.Id;

        IF @@ROWCOUNT <> @EXPECTED
        BEGIN
            ROLLBACK;
            PRINT 'row count differs from expected, rolled back';
        END
        ELSE
        BEGIN
            COMMIT;
            PRINT 'applied: ' + CAST(@EXPECTED AS varchar(20)) + ' row(s)';
        END
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        PRINT 'error, rolled back: ' + ERROR_MESSAGE();
    END CATCH
END
GO

PRINT '=== 4 rollback (off by default) ===';
DECLARE @RESTORE bit = 0;
IF @RESTORE = 1 AND OBJECT_ID('dbo.TargetTable_backup_20260101') IS NOT NULL
BEGIN
    BEGIN TRAN;
    UPDATE t SET t.Status = b.Status, t.UpdatedAt = b.UpdatedAt
    FROM dbo.TargetTable t
    JOIN dbo.TargetTable_backup_20260101 b ON b.Id = t.Id;
    PRINT 'restored: ' + CAST(@@ROWCOUNT AS varchar(20)) + ' row(s)';
    COMMIT;
END
ELSE
    PRINT 'rollback not requested';
GO

PRINT '=== 5 baseline after ===';
SELECT COUNT(*) AS rows_still_pending
FROM dbo.TargetTable t WITH (NOLOCK)
WHERE t.Status = 'PENDING' AND t.UpdatedAt < '2026-01-01';
GO
```

The reviewer checks that every section is present, that the simulation and the change use the same filter, that the switches default to `0`, and that the rollback restores exactly the rows that were saved.
