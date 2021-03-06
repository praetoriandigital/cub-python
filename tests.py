import time
from datetime import datetime
from os import getenv

try:
    from unittest.mock import patch, MagicMock
except ImportError:
    # py27 support
    from mock import patch, MagicMock

import pytest

from cub import User, config
from cub.models import (
    Country, CubObject, Group, Lead, Member, Message, Organization,
    UserSite, WebhookSubscription, objects_from_json,
)
from cub.exceptions import ConnectionError
from cub.timezone import utc
from cub.transport import urlify, _lib

skip_on_ci = pytest.mark.skipif(
    getenv('CI') == 'true',
    reason='Skipping this test on a CI.',
)
skip_on_urllib = pytest.mark.skipif(
    _lib != 'requests',
    reason='urllib does not support auto retry feature.',
)
config.api_key = getenv('INTEGRATION_TESTS_SECRET_KEY')

cub_obj = CubObject(id='cub_1')


@pytest.fixture
def user_data():
    return {
        'credentials': {
            'username': 'support@ivelum.com',
            'password': getenv('INTEGRATION_TESTS_USER_PASS'),
        },
        'details': {
            'original_username': 'ivelum',
            'first_name': 'do not remove of modify',
            'last_name': 'user for tests',
        }
    }


def test_objects_from_json():
    group_sample = {
        'object': 'group',
        'id': 42,
        'name': 'lol',
        'deleted': True
    }
    group = objects_from_json(group_sample)
    assert isinstance(group, Group)
    assert group.id == group_sample['id']
    assert group.name == group_sample['name']
    assert group.deleted == group_sample['deleted']


def test_user_login_and_get_by_token(user_data):
    user = User.login(**user_data['credentials'])
    for k, v in user_data['details'].items():
        assert v == getattr(user, k)
    assert isinstance(user.date_joined, datetime)
    utc_now = datetime.utcnow().replace(tzinfo=utc)
    assert user.date_joined < utc_now

    user2 = User.get(user.token)
    assert user2.username == user.username
    assert user2.first_name == user.first_name
    assert user2.last_name == user.last_name
    assert user2.date_joined == user.date_joined
    assert not user2.deleted


def test_user_reissue_token(user_data):
    user = User.login(**user_data['credentials'])
    token1 = user.token

    # make sure the new token has different expiration datetime
    # so, it will differ from previous token
    time.sleep(1)
    user.reissue_token()
    token2 = user.token
    user.reload()  # make sure we can access user data with new token
    assert token1 != token2

    time.sleep(1)
    # public key of Cub Admin and Demo app
    user.reissue_token(app_key='pk_PXobUgPbVGhA5fSyW')
    token3 = user.token
    user.reload()
    assert token2 != token3


@pytest.mark.parametrize(
    'site, status_code, message', [
        ('ste_mmIblyT4n3pmaABf', 200, 'Email has been sent'),
        (None, 400, 'The site field is required')
    ]
)
@patch('cub.transport.API.request')
def test_send_confirmation_email(request_mock, site, status_code, message):
    response_mock = MagicMock(status_code=status_code, message=message)
    request_mock.return_value = response_mock

    user = User(id='usr_upfrcJvCTyXCVBj8')

    response = user.send_confirmation_email(notification_site=site)

    assert request_mock.call_count == 1
    request_mock.assert_called_with(
        'post',
        '/users/{}/send-confirmation-email'.format(user.id),
        {'notification_site': site}
    )
    assert response.status_code == status_code
    assert response.message == message


def test_user_reload(user_data):
    user = User.login(**user_data['credentials'])
    try:
        user.reload(expand='membership__organization')
    except Exception as e:
        pytest.fail(e)

    assert len(user.membership) > 0
    member = user.membership[0]
    assert isinstance(member, Member)
    assert member.api_key == user.api_key
    assert isinstance(member.organization, Organization)
    assert member.organization.api_key == user.api_key
    assert not member.deleted


def test_organizations():
    organizations = Organization.list(count=2)
    assert len(organizations) <= 2
    for organization in organizations:
        assert organization.id is not None
        assert organization.name is not None
        org = Organization.get(id=organization.id)
        assert organization.name == org.name
        assert not organization.deleted


def test_countries():
    try:
        Country.list()
    except Exception as e:
        pytest.fail(e)


def test_leads():
    lead_data = {
        # LeadForm - [DEV] Integration Tests for LID client libs
        'form': 'lfm_yxBZF1bgiwKYdvrX',
        'cookie': 'value=key;thisis=theway;',
        'email': 'lid-tests@example.com',
        'first_name': 'Lid',
        'last_name': 'Tests',
        'url': 'http://localhost:9230/forms-demo/',
    }
    new_lead = Lead.create(**lead_data)
    new_lead.id is not None
    assert new_lead.email == lead_data['email']
    assert new_lead.form == lead_data['form']
    assert new_lead.data['first_name'] == lead_data['first_name']
    assert new_lead.site == 'ste_mmIblyT4n3pmaABf'  # localhost:9230

    leads = Lead.list(count=2)
    assert len(leads) <= 2
    for lead in leads:
        assert lead.data
        assert lead.id is not None
        assert lead.email is not None
        ld = Lead.get(id=lead.id)
        assert lead.email == ld.email
        assert not lead.deleted


def test_messages():
    messages = Message.list(count=2)

    assert len(messages) <= 2
    for message in messages:
        assert message.name
        assert message.id is not None
        ms = Message.get(id=message.id)
        assert message.name == ms.name
        assert not ms.deleted


def test_usersites(user_data):
    user = User.login(**user_data['credentials'])
    usersites = UserSite.list(user=user.id)
    assert len(usersites) > 1
    for usersite in usersites:
        assert usersite.site
        assert usersite.user
        assert usersite.last_seen
        assert usersite.first_seen
        assert usersite.is_active

        ust = UserSite.get(id=usersite.id)
        assert ust.site == usersite.site
        assert ust.user == usersite.user
        assert ust.last_seen == usersite.last_seen
        assert ust.first_seen == usersite.first_seen
        assert ust.is_active == usersite.is_active


@skip_on_ci
def test_webhooksubscriptions():
    ws = WebhookSubscription.create(instance='org_r0DY7pGnsSkUpZsM')
    ws = WebhookSubscription.get(id=ws.id)

    subscriptions = WebhookSubscription.list(count=2)
    assert 0 < len(subscriptions) <= 2
    for subscription in subscriptions:
        assert subscription.id is not None
        assert subscription.instance is not None
        assert subscription.application is not None
        assert not subscription.deleted

    ws.delete()


@skip_on_urllib
def test_api_connection_auto_retry(monkeypatch):
    start_time = time.time()
    monkeypatch.setattr(config, 'api_url', 'http://localhost:9999')
    with pytest.raises(ConnectionError):
        Organization.list(count=2)
    end_time = time.time()
    actual_time = end_time - start_time
    expected_time = 1.2  # backoff 0.2: 0 + 0.4 + 0.8
    assert actual_time >= expected_time


@pytest.mark.parametrize('data,expected', (
    ({'str': 'str', 'int': 1,
      'True': True, 'False': False, 'None': None,
      'true': 'true', 'false': 'false', 'null': 'null', 'number': '1'},
     {'str': 'str', 'int': 1,
      'True': 'true', 'False': 'false', 'None': 'null',
      'true': '"true"', 'false': '"false"', 'null': '"null"',
      'number': '"1"'}),
    ({'obj': CubObject(id='cub_1')},
     {'obj': 'cub_1'}),
    ({'dict': {'key': 'val'}},
     {'dict[key]': 'val'}),
    ({'dict': {'key': 'val'}},
     {'dict[key]': 'val'}),
    ({'list': [1, 'str', None], 'dict': {'dkey': 'dval'}, 'key': 'val'},
     {'list[0]': 1, 'list[1]': 'str', 'list[2]': 'null',
      'dict[dkey]': 'dval', 'key': 'val'}),
    ({'empty_list': [], 'empty_dict': {}},
     {}),
    ({'root': {'dict': ['val']}},
     {'root[dict][0]': 'val'}),
    ({'root': {'dict': ['val1', 'val2']}},
     {'root[dict][0]': 'val1', 'root[dict][1]': 'val2'}),
    ({'root': {'dict1': ['val1'], 'dict2': ['val2']}},
     {'root[dict1][0]': 'val1', 'root[dict2][0]': 'val2'}),
    ({'root': [{'key': 'val'}]},
     {'root[0][key]': 'val'}),
    ({'root': [[[1], 1], 1]},
     {'root[0][0][0]': 1, 'root[0][1]': 1, 'root[1]': 1}),
    ({'list': [
         {'name': 'John', 'age': 20},
         {'name': 'Kate', 'age': 18},
         {'name': 'Smith', 'age': 30},
     ]},
     {'list[0][name]': 'John', 'list[0][age]': 20,
      'list[1][name]': 'Kate', 'list[1][age]': 18,
      'list[2][name]': 'Smith', 'list[2][age]': 30}),
))
def test_nested_query(data, expected):
    assert urlify(data) == expected
