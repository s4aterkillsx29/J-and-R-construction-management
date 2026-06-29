import os
os.environ.setdefault('JRC_PUBLIC_HOST_MODE', '1')
os.environ.setdefault('JRC_CLOUD_PRIMARY_MODE', '1')
os.environ.setdefault('JRC_SESSION_TIMEOUT_MINUTES', '120')
os.environ.setdefault('JRC_DATA_DIR', '/var/data/jrc')
from app.network_server import app, init_db
init_db()
try:
    from app.data_pipeline import ensure_master_storage_layout, write_pipeline_manifest
    ensure_master_storage_layout()
    write_pipeline_manifest()
except Exception:
    pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', os.environ.get('JRC_PORT', '8765')))
    app.run(host='0.0.0.0', port=port)
