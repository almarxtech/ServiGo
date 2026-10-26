"""Safe, fixed visual treatments for provider-entered service category strings.

No database migration required; previously created categories work automatically.
Never render user-entered strings as raw CSS classes or icon class names.
"""
from django import template

register = template.Library()

_CATEGORY_MAP = (
    (('plumb', 'pipe', 'tap', 'water', 'drain', 'bathroom'), 'plumbing', 'fa-faucet-drip'),
    (('electric', 'wiring', 'light', 'switch', 'power'), 'electrical', 'fa-bolt'),
    (('clean', 'maid', 'housekeeping', 'laundry', 'saniti'), 'cleaning', 'fa-broom'),
    (('paint', 'decorat', 'wallpaper'), 'painting', 'fa-paint-roller'),
    (('carpent', 'wood', 'furnitur', 'cabinet'), 'carpentry', 'fa-hammer'),
    (('air condit', 'ac repair', 'a/c', 'hvac', 'cooling', 'heating', 'ventilat'), 'hvac', 'fa-snowflake'),
    (('appliance', 'washing machine', 'fridge', 'refrigerat', 'oven'), 'appliance', 'fa-kitchen-set'),
    (('garden', 'landscap', 'lawn', 'plant'), 'garden', 'fa-seedling'),
    (('pest', 'termite', 'insect', 'mosquito'), 'pest', 'fa-bug'),
    (('security', 'camera', 'cctv', 'lock'), 'security', 'fa-shield-halved'),
    (('mov', 'shift', 'transport', 'pack'), 'moving', 'fa-truck-fast'),
)


def _visual_for(category):
    text = ' '.join(str(category or '').casefold().split())
    for words, theme, icon in _CATEGORY_MAP:
        if any(word in text for word in words):
            return theme, icon
    return 'general', 'fa-screwdriver-wrench'


@register.filter(name='category_theme')
def category_theme(value):
    return _visual_for(value)[0]


@register.filter(name='category_icon')
def category_icon(value):
    return _visual_for(value)[1]
