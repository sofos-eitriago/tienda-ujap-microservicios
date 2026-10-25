# Prepara Windows para abrir el sistema en https://tienda.ujap.test
#   1) Agrega "tienda.ujap.test" al archivo hosts.
#   2) Confía en la CA local del gateway, para que el navegador muestre el candado sin advertencias.
#      Esa CA solo puede firmar tienda.ujap.test y localhost, y su clave privada se borró al crearla.
#      (Para el paso 2 el sistema tiene que estar levantado: docker compose up)
# Uso: clic derecho -> "Ejecutar con PowerShell"  (pedirá permiso de administrador)
#
# En Linux/macOS el paso 1 es:  echo "127.0.0.1 tienda.ujap.test" | sudo tee -a /etc/hosts

$dominio = "tienda.ujap.test"
$hosts = "$env:SystemRoot\System32\drivers\etc\hosts"

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    # Se vuelve a abrir a sí mismo con permisos de administrador
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

# 1) Archivo hosts
if (Select-String -Path $hosts -Pattern ([regex]::Escape($dominio)) -Quiet) {
    Write-Host "El archivo hosts ya tenia $dominio" -ForegroundColor Green
} else {
    Add-Content -Path $hosts -Value "`r`n127.0.0.1 $dominio" -Encoding ASCII
    ipconfig /flushdns | Out-Null
    Write-Host "Agregado $dominio al archivo hosts" -ForegroundColor Green
}

# 2) CA local del gateway (se copia desde el contenedor)
$ca = Join-Path $env:TEMP "ca-tienda-ujap.crt"
docker compose -f "$PSScriptRoot\docker-compose.yml" cp gateway:/etc/nginx/certificados/ca.crt $ca 2>$null
if ($LASTEXITCODE -eq 0 -and (Test-Path $ca)) {
    # Si el certificado se volvió a crear (p. ej. se borró el volumen), se quita la CA anterior
    Get-ChildItem Cert:\LocalMachine\Root | Where-Object Subject -like "*Tienda UJAP - CA local de desarrollo*" | Remove-Item
    Import-Certificate -FilePath $ca -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    Remove-Item $ca
    Write-Host "Listo: abre https://$dominio (si el navegador estaba abierto, reinicialo)" -ForegroundColor Green
} else {
    Write-Host "No se pudo leer el certificado: levanta el sistema (docker compose up) y vuelve a ejecutar este script." -ForegroundColor Yellow
    Write-Host "Mientras tanto puedes abrir https://$dominio aceptando la advertencia del navegador." -ForegroundColor Yellow
}
Start-Sleep -Seconds 5
