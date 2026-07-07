<#
  publicar_varios_powerbi.ps1
  Publica vários arquivos .pbix em um workspace do Power BI.

  Uso exemplo:
  powershell -NoProfile -ExecutionPolicy Bypass -File "C:\scripts\publicar_varios_powerbi.ps1" -WorkspaceName "MeuWorkspace" -Verbose

  Observação: o script busca arquivos usando variáveis ($env:OneDrive) se quiser publicar direto da sua OneDrive Área de Trabalho.
#>

param(
  [Parameter(Mandatory=$true)][string]$WorkspaceName,
  [string]$LogPath = "$PSScriptRoot\powerbi_publish_multi.log"
)

function Log {
  param($msg)
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $msg"
  Write-Output $line
  Add-Content -Path $LogPath -Value $line
}

# === Defina aqui os arquivos a publicar ===
# Pode usar caminhos absolutos ou construir com $env:OneDrive
$reportsToPublish = @(
  @{ Path = Join-Path $env:OneDrive "Área de Trabalho\BI-PONTUAL_basesql_teste.pbix"; Name = "BI-PONTUAL_basesql_teste" },
  @{ Path = Join-Path $env:OneDrive "Área de Trabalho\BI-TRANSBEN_SQL_TESTE.pbix"; Name = "BI-TRANSBEN_SQL_TESTE" }
)

try {
  Log "=== Iniciando publicação múltipla Power BI ==="
  Log "Workspace: $WorkspaceName"

  # Conectar (login interativo)
  Log "Solicitando login Power BI..."
  Connect-PowerBIServiceAccount -ErrorAction Stop

  # Buscar workspace
  $ws = Get-PowerBIWorkspace -Scope Organization | Where-Object { $_.Name -eq $WorkspaceName }
  if (-not $ws) { throw "Workspace não encontrado: $WorkspaceName" }
  Log "Workspace OK: $($ws.Id) - $($ws.Name)"

  foreach ($r in $reportsToPublish) {
    $pbix = $r.Path
    $rname = $r.Name
    Log "---- Processando: $rname | $pbix"

    if (-not (Test-Path $pbix)) {
      Log "AVISO: arquivo não encontrado: $pbix — pulando."
      continue
    }

    # Se houver relatório com mesmo nome, remove para evitar duplicatas
    $existing = Get-PowerBIReport -WorkspaceId $ws.Id | Where-Object { $_.Name -eq $rname }
    if ($existing) {
      Log "Relatório existente detectado (Id: $($existing.Id)). Removendo..."
      Remove-PowerBIReport -Id $existing.Id -WorkspaceId $ws.Id -Force
      Start-Sleep -Seconds 2
      Log "Removido."
    }

    Log "Publicando $rname..."
    $publish = Publish-PowerBIReport -Path $pbix -Name $rname -Workspace $ws.Id -ErrorAction Stop
    Log "Publicação OK. ReportId: $($publish.Id)"
  }

  Log "=== Publicação múltipla finalizada com sucesso ==="
  Exit 0
}
catch {
  Log "ERRO: $($_.Exception.Message)"
  Exit 1
}
finally {
  try { Disconnect-PowerBIServiceAccount -ErrorAction SilentlyContinue } catch {}
}