#!/usr/bin/env bash
# ElectroStock Başlatma Scripti

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "⚡ ElectroStock - Elektronik Parça & Stok Takip Sistemi ⚡"
echo "=========================================================="
echo ""
echo "📦 Veritabanı kontrol ediliyor..."
python3 -c "import electro_db; electro_db.init_db()"

echo ""
echo "🤖 MCP Server (Model Context Protocol) Bilgisi:"
echo "   Komut: python3 $SCRIPT_DIR/mcp_server.py"
echo "   Claude Desktop / Cursor için 'mcp_config_example.json' dosyasına bakabilirsiniz."
echo ""
echo "🌐 Web Arayüzü Başlatılıyor: http://localhost:8080"
echo "   (Durdurmak için Ctrl+C tuşlayabilirsiniz)"
echo "----------------------------------------------------------"
python3 web_app.py 8080
