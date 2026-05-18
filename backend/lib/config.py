import os

_DAN = 'dcjohnston1@gmail.com'
_EMILY = 'emily.osteen.johnston@gmail.com'

_PROJECT = 'mediationmate'
_LOCATION = 'us-central1'
_QUEUE = 'hana-actions'
_CLOUD_RUN_URL = os.environ.get(
    'CLOUD_RUN_URL',
    'https://saucer-backend-987132498395.us-central1.run.app',
)
_SA_EMAIL = os.environ.get(
    'CLOUD_TASKS_SERVICE_ACCOUNT',
    'saucer-doc-service@mediationmate.iam.gserviceaccount.com',
)
_PUBSUB_TOPIC = 'projects/mediationmate/topics/saucer-gmail-push'
