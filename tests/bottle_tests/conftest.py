import sys
import fenrir.bottle

# Force sys.modules['bottle'] to be fenrir.bottle
sys.modules['bottle'] = fenrir.bottle
