$src = 'E:\stock5'
$dest = 'E:\stock5\src'

$excludeDirs = @('src','run','.git','.codegraph','__pycache__','backup','logs','graphify-out','model_cache_v5','model_cache_v6','v6\model_cache_v6','catboost_info','browser-profile')
$excludeFiles = @('stocks.db','stocks.db.bak','collection.pid','em_fetcher.pid','factor_collection.pid','web_server.pid')

Get-ChildItem -Path $src -File | Where-Object { $_.Name -notin $excludeFiles } | ForEach-Object {
    Copy-Item $_.FullName -Destination $dest -Force
    Write-Host "Copied: $($_.Name)"
}

Get-ChildItem -Path $src -Directory | Where-Object { $_.Name -notin $excludeDirs } | ForEach-Object {
    if (-not (Test-Path (Join-Path $dest $_.Name))) {
        Copy-Item $_.FullName -Destination $dest -Recurse -Force
        Write-Host "Copied dir: $($_.Name)"
    }
}

Write-Host "Done!"