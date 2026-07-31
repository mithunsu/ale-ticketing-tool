#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the ticket_comments schema tests against a disposable PostgreSQL database.

.DESCRIPTION
    Creates a temporary PostgreSQL database inside the running Docker container,
    applies the full schema, runs ticket_comments_tests.sql, then removes the
    temporary database on both success and failure.

    The real ale_ticketing database is never touched.

.PARAMETER ContainerName
    Name of the running PostgreSQL Docker container.
    Default: ale_ticketing_postgres

.PARAMETER DatabaseUser
    PostgreSQL user to use for all commands.
    Default: ale_ticket_user

.EXAMPLE
    # Run from the project root:
    .\database\tests\run_ticket_comments_tests.ps1
#>

[CmdletBinding()]
param(
    [string] $ContainerName = 'ale_ticketing_postgres',
    [string] $DatabaseUser  = 'ale_ticket_user'
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Path resolution — always relative to this script file, not the working
# directory the caller used.
# ---------------------------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Resolve-Path (Join-Path $ScriptDir '..\..')
$SchemaFile = Join-Path $RepoRoot 'database\schema.sql'
$TestFile   = Join-Path $ScriptDir 'ticket_comments_tests.sql'

# ---------------------------------------------------------------------------
# Tracking variable: only attempt cleanup if the DB was created successfully.
# ---------------------------------------------------------------------------
$TempDb = $null

# ---------------------------------------------------------------------------
# Helper: run a docker exec command and throw on non-zero exit.
# ---------------------------------------------------------------------------
function Invoke-Docker {
    param([string[]] $Arguments, [string] $Description)

    docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed ($Description). Exit code: $LASTEXITCODE"
    }
}

# ---------------------------------------------------------------------------
# Helper: pipe a local file into psql running inside the container.
# ---------------------------------------------------------------------------
function Invoke-PsqlFile {
    param(
        [string] $FilePath,
        [string] $Database,
        [string] $Description
    )

    $sql = Get-Content -Raw $FilePath
    $sql | docker exec -i $ContainerName `
        psql -U $DatabaseUser -d $Database -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) {
        throw "psql command failed ($Description). Exit code: $LASTEXITCODE"
    }
}

try {
    # -----------------------------------------------------------------------
    # 1. Verify required files exist
    # -----------------------------------------------------------------------
    Write-Host ''
    Write-Host '-- Verifying required files'

    if (-not (Test-Path $SchemaFile)) {
        throw "Schema file not found: $SchemaFile"
    }
    if (-not (Test-Path $TestFile)) {
        throw "Test file not found: $TestFile"
    }
    Write-Host "   schema : $SchemaFile"
    Write-Host "   tests  : $TestFile"

    # -----------------------------------------------------------------------
    # 2. Verify Docker is available
    # -----------------------------------------------------------------------
    Write-Host ''
    Write-Host '-- Checking Docker'

    docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker is not available or Docker Desktop is not running.'
    }
    Write-Host '   Docker is available'

    # -----------------------------------------------------------------------
    # 3. Verify the PostgreSQL container is running
    # -----------------------------------------------------------------------
    $ContainerState = docker inspect --format '{{.State.Running}}' $ContainerName 2>&1
    if ($LASTEXITCODE -ne 0 -or $ContainerState -ne 'true') {
        throw "Container '$ContainerName' is not running. Start it with: docker compose up -d"
    }
    Write-Host "   Container '$ContainerName' is running"

    # -----------------------------------------------------------------------
    # 4. Generate a unique, safe temporary database name
    # -----------------------------------------------------------------------
    $Timestamp = (Get-Date -Format 'yyyyMMddHHmmss')
    $TempDb    = "ale_ticketing_schema_test_$Timestamp"

    # Validate name contains only lowercase letters, digits, and underscores.
    if ($TempDb -notmatch '^[a-z0-9_]+$') {
        throw "Generated database name '$TempDb' contains unexpected characters."
    }
    Write-Host ''
    Write-Host "-- Creating temporary database: $TempDb"

    Invoke-Docker `
        -Arguments @('exec', $ContainerName, 'createdb', '-U', $DatabaseUser, $TempDb) `
        -Description "createdb $TempDb"

    Write-Host "   Created: $TempDb"

    # -----------------------------------------------------------------------
    # 5. Apply the full schema
    # -----------------------------------------------------------------------
    Write-Host ''
    Write-Host '-- Applying schema'

    Invoke-PsqlFile `
        -FilePath    $SchemaFile `
        -Database    $TempDb `
        -Description "apply schema.sql"

    Write-Host '   Schema applied successfully'

    # -----------------------------------------------------------------------
    # 6. Run ticket_comments tests
    # -----------------------------------------------------------------------
    Write-Host ''
    Write-Host '-- Running ticket_comments tests'

    Invoke-PsqlFile `
        -FilePath    $TestFile `
        -Database    $TempDb `
        -Description "ticket_comments_tests.sql"

    # -----------------------------------------------------------------------
    # 7. All tests passed
    # -----------------------------------------------------------------------
    Write-Host ''
    Write-Host '-- Tests passed'
    Write-Host ''
    Write-Host 'PASS: ticket_comments schema tests completed successfully.'
    Write-Host ''

    exit 0
}
catch {
    Write-Host ''
    Write-Host "FAIL: $_"
    Write-Host ''
    exit 1
}
finally {
    # -----------------------------------------------------------------------
    # Cleanup - always runs, success or failure.
    # Only proceeds if the temporary database was actually created.
    # -----------------------------------------------------------------------
    if ($null -ne $TempDb) {

        # Safety check: refuse to drop anything that is not a test database.
        if ($TempDb -notlike 'ale_ticketing_schema_test_*') {
            Write-Host ''
            Write-Host ('SAFETY: Refusing to drop ''{0}'' - name does not start with ''ale_ticketing_schema_test_''.' -f $TempDb)
        }
        else {
            Write-Host ''
            Write-Host ('-- Removing temporary database: {0}' -f $TempDb)

            # Terminate any remaining connections to the temporary database.
            # Connect to the postgres maintenance database, not to TempDb.
            $TerminateSql = 'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = ''{0}'' AND pid <> pg_backend_pid();' -f $TempDb
            $TerminateSql | docker exec -i $ContainerName `
                psql -U $DatabaseUser -d postgres -v ON_ERROR_STOP=1 | Out-Null

            # Drop the temporary database.
            docker exec $ContainerName `
                dropdb -U $DatabaseUser --if-exists $TempDb

            if ($LASTEXITCODE -eq 0) {
                Write-Host ('   Removed: {0}' -f $TempDb)
            }
            else {
                Write-Host ('   WARNING: dropdb returned exit code {0} for ''{1}''.' -f $LASTEXITCODE, $TempDb)
                Write-Host '   You may need to remove it manually:'
                Write-Host ('   docker exec {0} dropdb -U {1} {2}' -f $ContainerName, $DatabaseUser, $TempDb)
            }
        }
    }
}
