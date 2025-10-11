Param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('up','down','logs','migrate','seed','seed_demo','ps')]
  [string]$Task
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$compose = "docker compose -f infra/docker-compose.yml"

switch ($Task) {
  'up'      { iex "$compose up -d --build" }
  'down'    { iex "$compose down -v" }
  'logs'    { iex "$compose logs -f --tail=200 api bot worker db redis nginx" }
  'ps'      { iex "$compose ps" }
  'migrate' {
      iex "$compose up -d db"
      Start-Sleep -Seconds 3
      # run in one-off container to avoid 'service is not running' race
      iex "$compose run --rm api sh -lc 'export PYTHONPATH=/app; alembic -c app/db/alembic.ini upgrade head'"
  }
  'seed'    {
      iex "$compose up -d db"
      Start-Sleep -Seconds 2
      iex "$compose run --rm api sh -lc 'python -m app.scripts.seed'"
  }
  'seed_demo'    {
      iex "$compose up -d db"
      Start-Sleep -Seconds 2
      iex "$compose run --rm api sh -lc 'python -m app.scripts.seed_demo_events'"
  }
  default   { Write-Error "Unknown task: $Task" }
}
