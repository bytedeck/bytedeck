from django.dispatch import Signal

# providing_args=['recipient', 'verb', 'action', 'target', 'affected_users', 'icon']
notify = Signal()
