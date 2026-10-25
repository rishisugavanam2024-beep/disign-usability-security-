from examples.django_admin.settings import *  # noqa: F403

# These existing tests start with ordinary Django authentication. The plugin
# enables tracing only for each observed test body and then restores settings.
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
SAFEREVOKE_TEST_ENVIRONMENT = False
