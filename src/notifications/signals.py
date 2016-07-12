from django.dispatch import Signal

notify = Signal(providing_args=['recipient', 'verb', 'action', 'target', 'affected_users', 'icon'])
