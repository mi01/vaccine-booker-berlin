import sys
import re
import logging
import tempfile
from time import sleep
import json
import datetime
import argparse
import getpass
import cloudscraper

from enum import Enum
from urllib.parse import urlparse
from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
from requests.exceptions import Timeout
from termcolor import colored
from woob.browser.exceptions import ClientError, ServerError, HTTPNotFound
from woob.browser.browsers import LoginBrowser
from woob.browser.url import URL
from woob.browser.pages import JsonPage, HTMLPage


def log(text, *args, **kwargs):
    args = (colored(arg, 'yellow') for arg in args)
    if 'color' in kwargs:
        text = colored(text, kwargs.pop('color'))
    text = text % tuple(args)
    print('::: ', text, **kwargs)


class VaccinationStep(Enum):
    first = 'first'
    second = 'second'
    booster = 'booster'

    def __str__(self):
        return self.value


class Session(cloudscraper.CloudScraper):
    def send(self, *args, **kwargs):
        callback = kwargs.pop('callback', lambda future, response: response)
        is_async = kwargs.pop('is_async', False)

        if is_async:
            raise ValueError('Async requests are not supported')

        resp = super().send(*args, **kwargs)

        return callback(self, resp)


class LoginPage(JsonPage):
    def redirect(self):
        return self.doc['redirection']


class SendAuthCodePage(JsonPage):
    def build_doc(self, content):
        return ""  # Do not choke on empty response from server


class ChallengePage(JsonPage):
    def build_doc(self, content):
        return ""  # Do not choke on empty response from server


class CenterBookingPage(JsonPage):
    def find_motives(self, regex):
        motives = {}
        for s in self.doc['data']['visit_motives']:
            if re.search(regex, s['name']):
                motives[s['name']] = s['id']
        return motives

    def get_motives(self):
        return [s['name'] for s in self.doc['data']['visit_motives']]

    def get_places(self):
        return self.doc['data']['places']

    def get_practice(self):
        return self.doc['data']['places'][0]['practice_ids'][0]

    def get_agenda_ids(self, motive_id, practice_id=None):
        agenda_ids = []
        for a in self.doc['data']['agendas']:
            if motive_id in a['visit_motive_ids'] and \
               not a['booking_disabled'] and \
               (not practice_id or a['practice_id'] == practice_id):
                agenda_ids.append(str(a['id']))

        return agenda_ids

    def get_profile_id(self):
        return self.doc['data']['profile']['id']


class AvailabilitiesPage(JsonPage):
    def find_best_first_slot(self, start_date, time_window):
        for a in self.doc['availabilities']:
            d = parse_date(a['date']).date()
            if d < start_date or d > start_date + relativedelta(days=time_window):
                continue

            if len(a['slots']) == 0:
                continue
            return a['slots'][-1]

    def find_best_second_slot(self):
        for a in self.doc['availabilities']:
            if len(a['slots']) == 0:
                continue
            return a['slots'][-1]


class AppointmentPage(JsonPage):
    def get_error(self):
        return self.doc['error']

    def is_error(self):
        return 'error' in self.doc


class AppointmentEditPage(JsonPage):
    def get_custom_fields(self):
        for field in self.doc['appointment']['custom_fields']:
            if field['required']:
                yield field


class AppointmentPostPage(JsonPage):
    pass


class MasterPatientPage(JsonPage):
    def get_patients(self):
        return self.doc

    def get_name(self):
        return '%s %s' % (self.doc[0]['first_name'], self.doc[0]['last_name'])


class Doctolib(LoginBrowser):
    BASEURL = 'https://www.doctolib.de'

    login = URL('/login.json', LoginPage)
    send_auth_code = URL(r'/api/accounts/send_auth_code', SendAuthCodePage)
    challenge = URL(r'/login/challenge', ChallengePage)
    center_booking = URL(r'booking/ciz-berlin-berlin.json', CenterBookingPage)
    availabilities = URL(r'/availabilities.json', AvailabilitiesPage)
    appointment = URL(r'/appointments.json', AppointmentPage)
    appointment_edit = URL(
        r'/appointments/(?P<id>.+)/edit.json', AppointmentEditPage)
    appointment_post = URL(
        r'/appointments/(?P<id>.+).json', AppointmentPostPage)
    master_patient = URL(r'/account/master_patients.json', MasterPatientPage)

    def _setup_session(self, profile):
        session = Session()

        session.hooks['response'].append(self.set_normalized_url)
        if self.responses_dirname is not None:
            session.hooks['response'].append(self.save_response)

        self.session = session

    def __init__(self, *args, step, start_date, time_window, excluded_centers, **kwargs):
        super().__init__(*args, **kwargs)
        self.session.headers['sec-fetch-dest'] = 'document'
        self.session.headers['sec-fetch-mode'] = 'navigate'
        self.session.headers['sec-fetch-site'] = 'same-origin'
        self.session.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36'

        s = ''
        if step == VaccinationStep.first:
            s = 'Erstimpfung'
        elif step == VaccinationStep.second:
            s = 'Zweitimpfung'
        else:
            s = 'Auffrischung'

        self._motive_filter = '(' + s + ')'
        self._logged = False
        self.patient = None
        self.step = step
        self.start_date = start_date
        self.time_window = time_window
        self.excluded_centers = excluded_centers

    @property
    def logged(self):
        return self._logged

    def do_login(self):
        try:
            self.open(self.BASEURL + '/sessions/new')
        except ServerError as e:
            if e.response.status_code in [503] \
                and 'text/html' in e.response.headers['Content-Type'] \
                    and ('cloudflare' in e.response.text or 'Checking your browser before accessing' in e .response.text):
                log('Request blocked by CloudFlare. Try again!', color='red')
            return False
        try:
            self.login.go(json={'kind': 'patient',
                                'username': self.username,
                                'password': self.password,
                                'remember': True,
                                'remember_username': True})
        except ClientError:
            log('Wrong login/password!', color='red')
            return False

        if self.page.redirect() == "/sessions/two-factor":
            log("Requesting 2fa code ...")
            self.send_auth_code.go(
                json={'two_factor_auth_method': 'email'}, method="POST")
            code = input("Enter auth code: ")
            try:
                self.challenge.go(
                    json={'auth_code': code, 'two_factor_auth_method': 'email'}, method="POST")
            except HTTPNotFound:
                log("Invalid auth code!", color='red')
                return False

        return True

    def get_patients(self):
        try:
            self.master_patient.go()
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return None

        return self.page.get_patients()

    def try_to_book(self, dry_run=False):
        try:
            center_page = self.center_booking.go()
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return False

        profile_id = self.page.get_profile_id()
        motives = self.page.find_motives(
            r'{}'.format(self._motive_filter))

        if not motives:
            log('Unable to find vaccination motive', color='red')
            log('Available motives: %s', ', '.join(self.page.get_motives()))
            return False

        for place in self.page.get_places():
            if any(center in place['name'] for center in self.excluded_centers):
                continue
            log('Looking for slots in place %s', place['name'])
            for motive_name, motive_id in motives.items():
                practice_id = place['practice_ids'][0]
                agenda_ids = center_page.get_agenda_ids(
                    motive_id, practice_id)
                if len(agenda_ids) == 0:
                    continue

                log('Motive: %s ...', motive_name)
                if self.try_to_book_place(profile_id, motive_id, practice_id, agenda_ids, dry_run):
                    return True

        return False

    def try_to_book_place(self, profile_id, motive_id, practice_id, agenda_ids, dry_run=False):
        date = datetime.date.today().strftime('%Y-%m-%d')
        while date is not None:
            try:
                self.availabilities.go(params={'start_date': date,
                                               'visit_motive_ids': motive_id,
                                               'agenda_ids': '-'.join(agenda_ids),
                                               'insurance_sector': 'public',
                                               'practice_ids': practice_id,
                                               'destroy_temporary': 'true',
                                               'limit': 3})
            except Exception as err:
                log('Error: %s', str(err), color='red')
                return False

            if 'next_slot' in self.page.doc:
                date = self.page.doc['next_slot']
            else:
                date = None

        if len(self.page.doc['availabilities']) == 0 or self.page.doc['total'] == 0:
            log('No availabilities in this center', color='red')
            return False

        slot = self.page.find_best_first_slot(
            self.start_date, self.time_window)
        if not slot:
            log('First slot not found :(', color='red')
            return False

        start_date = slot
        if isinstance(slot, dict):
            start_date = slot['start_date']
        log('Best slot found: %s', parse_date(
            start_date).strftime('%c'), color='green')

        appointment = {'profile_id':    profile_id,
                       'source_action': 'profile',
                       'start_date':    start_date,
                       'visit_motive_ids': str(motive_id),
                       }

        data = {'agenda_ids': '-'.join(agenda_ids),
                'appointment': appointment,
                'practice_ids': [practice_id]}

        headers = {
            'content-type': 'application/json',
        }

        try:
            self.appointment.go(data=json.dumps(data), headers=headers)
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return False

        if self.page.is_error():
            log('Appointment not available anymore :( %s',
                self.page.get_error(), color='red')
            return False

        if self.step == VaccinationStep.first:
            try:
                self.availabilities.go(params={'start_date': slot['steps'][1]['start_date'].split('T')[0],
                                               'visit_motive_ids': motive_id,
                                               'agenda_ids': '-'.join(agenda_ids),
                                               'first_slot': slot['start_date'],
                                               'insurance_sector': 'public',
                                               'practice_ids': practice_id,
                                               'limit': 3})
            except Exception as err:
                log('Error: %s', str(err), color='red')
                return False

            second_slot = self.page.find_best_second_slot()
            if not second_slot:
                log('No second shot found!', color='red')
                return False

            log('Second shot: %s', parse_date(
                second_slot['start_date']).strftime('%c'), color='green')

            data['second_slot'] = second_slot['start_date']
            try:
                self.appointment.go(data=json.dumps(data), headers=headers)
            except Exception as err:
                log('Error: %s', str(err), color='red')
                return False

            if self.page.is_error():
                log('Appointment not available anymore :( %s',
                    self.page.get_error(), color='red')
                return False

        a_id = self.page.doc['id']

        try:
            self.appointment_edit.go(id=a_id)
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return False

        log('Booking for %s %s...',
            self.patient['first_name'], self.patient['last_name'])

        try:
            self.appointment_edit.go(
                id=a_id, params={'master_patient_id': self.patient['id']})
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return False

        custom_fields = {}
        for field in self.page.get_custom_fields():
            if field['id'].find('cov19') != -1:
                value = 'Nein'
            elif field['label'].find('Geschlecht') != -1:
                value = 'w' if self.patient['gender'] else 'm'
            elif field['placeholder']:
                value = field['placeholder']
            else:
                print('%s (%s):' %
                      (field['label'], field['placeholder']), end=' ', flush=True)
                value = sys.stdin.readline().strip()

            custom_fields[field['id']] = value

        data = {'appointment': {'custom_fields_values': custom_fields,
                                'new_patient': True,
                                'qualification_answers': {},
                                'referrer_id': None,
                                'start_date': start_date,
                                },
                'bypass_mandatory_relative_contact_info': False,
                'email': None,
                'master_patient': self.patient,
                'new_patient': True,
                'patient': None,
                'phone_number': None,
                }

        # Doctolib does not seem to check the token
        # headers['x-csrf-token'] = self.page.response.headers['x-csrf-token']

        if dry_run:
            log('Booking status: %s', 'fake')
            return True

        try:
            self.appointment_post.go(id=a_id, data=json.dumps(
                data), headers=headers, method='PUT')
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return False

        if 'redirection' in self.page.doc:
            log('Go on %s to complete', self.BASEURL +
                self.page.doc['redirection'])

        try:
            self.appointment_post.go(id=a_id)
        except Exception as err:
            log('Error: %s', str(err), color='red')
            return False

        confirmation_color = 'green' if self.page.doc['confirmed'] else 'red'
        log('Booking status: %s',
            self.page.doc['confirmed'], color=confirmation_color)

        return self.page.doc['confirmed']


def main():
    parser = argparse.ArgumentParser(
        description="Book a vaccination slot on Doctolib in Berlin")
    parser.add_argument('step', type=VaccinationStep,
                        choices=list(VaccinationStep))
    parser.add_argument('--debug', '-d', action='store_true',
                        help='show debug information')
    parser.add_argument('--dry-run', action='store_true',
                        help='do not really book the slot')
    parser.add_argument('--start-date', type=datetime.date.fromisoformat,
                        help='Start date of search period (yyyy-mm-dd)')
    parser.add_argument('--time-window', type=int, default=14,
                        help='Length of the search period in of days after the start date')
    parser.add_argument('--exclude-messe', action='store_true',
                        help='Exclude center at Messe Berlin')
    parser.add_argument('--exclude-tegel', action='store_true',
                        help='Exclude center at Flughafen Tegel')
    parser.add_argument('--exclude-ring-center', action='store_true',
                        help='Exclude center at Ring-Center')
    parser.add_argument('--exclude-karlshorst', action='store_true',
                        help='Exclude center at Trabrennbahn Karlshorst')
    parser.add_argument('username', help='Doctolib username')
    parser.add_argument('password', nargs='?', help='Doctolib password')
    args = parser.parse_args()

    if not args.password:
        args.password = getpass.getpass()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        responses_dirname = tempfile.mkdtemp(prefix='woob_session_')
    else:
        responses_dirname = None

    start_date = datetime.date.today() if not args.start_date else args.start_date

    excluded_centers = []
    if args.exclude_messe:
        excluded_centers.append('Messe')
    if args.exclude_tegel:
        excluded_centers.append('Tegel')
    if args.exclude_ring_center:
        excluded_centers.append('Ring')
    if args.exclude_karlshorst:
        excluded_centers.append('Karlshorst')

    docto = Doctolib(args.username, args.password, step=args.step, start_date=start_date, time_window=args.time_window,
                     excluded_centers=excluded_centers, responses_dirname=responses_dirname)
    if not docto.do_login():
        print('Could not login!')
        return 1

    patients = docto.get_patients()
    if patients is None:
        return 1
    elif len(patients) == 0:
        print("Please fill your patient data on Doctolib website.")
        return 1
    elif len(patients) > 1:
        print('Available patients are:')
        for i, patient in enumerate(patients):
            print('* [%s] %s %s' %
                  (i, patient['first_name'], patient['last_name']))
        while True:
            print('You want to book a slot for whom patient?', end=' ', flush=True)
            try:
                docto.patient = patients[int(sys.stdin.readline().strip())]
            except (ValueError, IndexError):
                continue
            else:
                break
    else:
        docto.patient = patients[0]

    if not docto.patient['phone_number'] or docto.patient['phone_number'] == '':
        # Booking fails without a phone number
        print("Please enter the phone number of the patient on the Doctolib website.")
        return 1

    while True:
        if docto.try_to_book(args.dry_run):
            log('Booked!')
            return 0
        sleep(1)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Abort.')
        sys.exit(1)
