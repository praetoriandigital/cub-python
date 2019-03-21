from datetime import datetime
from unittest import TestCase

import pytest

from cub import config, User
from cub.models import Organization, Member, Group, \
    objects_from_json, Country, Lead, CubObject
from cub.timezone import utc
from cub.transport import urlify


class APITest(TestCase):
    def setUp(self):
        config.api_key = 'sk_23a00c357cb44c358'
        self.test_user = {
            'credentials': {
                'username': 'support@ivelum.com',
                'password': 'SJW8Gg',
            },
            'details': {
                'original_username': 'ivelum',
                'first_name': 'do not remove of modify',
                'last_name': 'user for tests',
            }
        }

    def test_objects_from_json(self):
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

    def test_user_login_and_get_by_token(self):
        user = User.login(**self.test_user['credentials'])
        for k, v in self.test_user['details'].items():
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

    def test_user_reload(self):
        user = User.login(**self.test_user['credentials'])
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

    def test_organizations(self):
        organizations = Organization.list(count=2)
        assert len(organizations) <= 2
        for organization in organizations:
            assert organization.id is not None
            assert organization.name is not None
            org = Organization.get(id=organization.id)
            assert organization.name == org.name
            assert not organization.deleted

    def test_countries(self):
        try:
            Country.list()
        except Exception as e:
            pytest.fail(e)

    def test_leads(self):
        leads = Lead.list(count=2)
        assert len(leads) <= 2
        for lead in leads:
            assert lead.data
            assert lead.id is not None
            assert lead.email is not None
            ld = Lead.get(id=lead.id)
            assert lead.email == ld.email
            assert not lead.deleted

    def test_nested_query(self):
        cub_obj = CubObject(id='cub_1')
        cases = (
            ({'str': 'str', 'int': 1,
              'True': True, 'False': False, 'None': None,
              'true': 'true', 'false': 'false', 'null': 'null', 'number': '1'},
             {'str': 'str', 'int': 1,
              'True': 'true', 'False': 'false', 'None': 'null',
              'true': '"true"', 'false': '"false"', 'null': '"null"',
              'number': '"1"'}),
            ({'obj': cub_obj},
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
        )
        for data, expected in cases:
            assert urlify(data) == expected
