# Agrega "tienda.ujap.test" al archivo hosts de Windows para abrir el sistema en http://tienda.ujap.test
# Uso: clic derecho -> "Ejecutar con PowerShell"  (pedirá permiso de administrador)
#
# En Linux/macOS el equivalente es:  echo "127.0.0.1 tienda.ujap.test" | sudo tee -a /etc/hosts

$dominio = "tienda.ujap.test"
$hosts = "$env:SystemRoot\System32\drivers\etc\hosts"

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    # Se vuelve a abrir a sí mismo con permisos de administrador
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

if (Select-String -Path $hosts -Pattern ([regex]::Escape($dominio)) -Quiet) {
    Write-Host "Ya estaba configurado: http://$dominio" -ForegroundColor Green
} else {
    Add-Content -Path $hosts -Value "`r`n127.0.0.1 $dominio" -Encoding ASCII
    ipconfig /flushdns | Out-Null
    Write-Host "Listo: ahora puedes abrir http://$dominio" -ForegroundColor Green
}
Start-Sleep -Seconds 3
