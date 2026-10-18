"""Grounded, read-only Jira assignee/work queries without model-invented IDs."""
from main.src.utils.enums import ResultStatus
from main.src.utils import regex_constants as rx
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

def payload(result):
    content = result['content']
    if isinstance(content, list):
        blocks = [block.get('text') for block in content if isinstance(block, dict) and block.get('type') == 'text']
        content = blocks[0] if len(blocks) == 1 else blocks
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return {}
    if isinstance(content, dict):
        return content.get('data', content)
    return content


def work_subject(question):
    text = question.strip().rstrip('?.!')
    match = re.search(rx.JIRA_PERSON_WORK, text, re.I)
    if match:
        return match[1].strip()
    if re.search(rx.JIRA_OWN_WORK, text, re.I):
        return 'me' if not re.search(rx.JIRA_OUR_WORK, text, re.I) else None
    if re.search(rx.JIRA_MY_WORK, text, re.I):
        return 'me'
    return None


def normalized(value):
    return ' '.join(str(value).casefold().split())


def quote_jql(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def cell(value):
    # Jira strings are display data, never Markdown instructions.
    return (str(value)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('|', '\\|')
            .replace('\n', ' ')
            .replace('[', '\\[')
            .replace(']', '\\]'))


def due_label(fields):
    if 'duedate' not in fields:
        return 'Not returned by Jira'
    if not fields['duedate']:
        return 'Not set'
    try:
        value = date.fromisoformat(fields['duedate'])
        return f'{value.day} {value.strftime("%B %Y")}'
    except (ValueError, TypeError):
        return 'Invalid due date returned'


async def assigned_work(question, config, execute):
    """Return None for unrelated questions; execute is a validated MCP read call."""
    subject = work_subject(question)
    if subject is None:
        return None
    evidence = []

    async def read(tool, arguments):
        result = await execute(tool, arguments)
        evidence.append(result)
        if result['is_error']:
            raise ValueError(f'Jira read failed: {tool}')
        data = payload(result)
        if isinstance(data, dict) and data.get('error'):
            raise ValueError(f'Jira returned an error: {tool}')
        return data

    def outcome(answer, status=ResultStatus.ANSWERED, issues=None):
        return {
            'status': status,
            'answer': answer,
            'tools_used': [f'jira:{item["tool"]}' for item in evidence],
            'support': [],
            'results': [],
            'mcp_evidence': evidence,
            'jira_issues': issues or [],
            'notices': [
                'Connected directly to Jira. Active means Jira status category In Progress,'
                ' including review and testing.'
            ]
        }

    try:
        resources = await read('getAccessibleAtlassianResources', {})
        site = config.get('context', {}).get('site_url', '').rstrip('/')
        sites = resources.get('resources', []) if isinstance(resources, dict) else resources
        matches = [item for item in (sites or []) if isinstance(item, dict) and item.get('url', '').rstrip('/') == site]
        if len(matches) != 1 or not matches[0].get('cloudId'):
            return outcome(
                'The configured Jira site was not uniquely available to your account.',
                ResultStatus.INSUFFICIENT_EVIDENCE
            )
        cloud_id = matches[0]['cloudId']
        current = await read('getJiraCurrentUser', {'cloudId': cloud_id})
        user = current
        if normalized(subject) not in {'me', 'i', 'myself', normalized(current.get('displayName', '')), normalized(current.get('emailAddress', ''))}:
            found = await read('lookupJiraAccountId', {
                'cloudId': cloud_id,
                'query': subject,
                'maxResults': 10
            })
            candidates = found if isinstance(found, list) else found.get('users', found.get('results', []))
            exact = [person for person in candidates if normalized(subject) in
                     {normalized(person.get('displayName', '')), normalized(person.get('emailAddress', ''))}]
            if len(exact) != 1:
                return outcome('I could not uniquely identify that Jira user. Provide their full display name or email.', ResultStatus.NEEDS_CLARIFICATION)
            user = exact[0]
        account = user.get('accountId')
        if not account:
            return outcome(
                'Jira did not return an account ID for that user.',
                ResultStatus.INSUFFICIENT_EVIDENCE
            )
        project = config.get('context', {}).get('project_key')
        explicit = re.search(rx.JIRA_PROJECT, question)
        if explicit: project = explicit[1]
        scope = f'project = {quote_jql(project)} AND ' if project else ''
        jql = scope + f'assignee = {quote_jql(account)} AND statusCategory = "In Progress" ORDER BY duedate ASC, updated DESC'
        search = await read(
            'searchJiraIssuesUsingJql',
            {
                'cloudId': cloud_id,
                'jql': jql,
                'maxResults': 10,
                'fields': [
                    'summary',
                    'status',
                    'duedate',
                    'assignee'
                ],
                'view': 'full'
            }
        )
        if not isinstance(search, dict) or not isinstance(search.get('issues'), list):
            return outcome(
                'Jira did not return a usable issue search result.',
                ResultStatus.INSUFFICIENT_EVIDENCE
            )
        issues = search['issues'][:10]
        rows = []
        for issue in issues:
            key, fields = issue.get('key'), issue.get('fields', {})
            if not key or not re.fullmatch(rx.JIRA_ISSUE_KEY, key):
                continue
            # Search views may drop duedate even when explicitly requested. Only
            # a full detail response can distinguish missing data from an unset date.
            if 'duedate' not in fields:
                try:
                    detail = await read('getJiraIssue', {
                        'cloudId': cloud_id,
                        'issueIdOrKey': key,
                        'fields': [
                            'summary',
                            'status',
                            'duedate',
                            'assignee'
                        ],
                        'view': 'full'
                    })
                    if isinstance(detail, dict) and detail.get('key') == key:
                        fields = {**fields, **detail.get('fields', {})}
                except ValueError:
                    pass  # Keep the search evidence; label the missing date accurately.
            assignee = fields.get('assignee') or {}
            if assignee.get('accountId') != account:
                continue
            status = fields.get('status') or {}
            category = status.get('statusCategory') or {}
            if category.get('name') and category['name'] != 'In Progress':
                continue
            rows.append({
                'key': key,
                'summary': fields.get('summary', ''),
                'status': status.get('name', 'Unknown'),
                'due_date': fields.get('duedate'),
                'due_date_returned': 'duedate' in fields,
                'due_label': due_label(fields),
                'url': site + '/browse/' + key
            })
        label = cell(user.get('displayName', subject))
        project_label = cell(project or 'accessible projects')
        if not rows:
            if issues:
                return outcome(
                    'The returned issues did not contain verified assignee information.',
                    ResultStatus.INSUFFICIENT_EVIDENCE
                )
            return outcome(
                f'No active issues were found for {label} in {project_label}. '
                f'This excludes To Do and Done issues.'
            )
        rows.sort(key=lambda row: (row['status'].casefold() != 'in progress', row['due_date'] or '9999-12-31'))
        answer = f'{label} has {len(rows)} active issues in {project_label}:\n\n| Issue | Work | Status | Due date |\n| --- | --- | --- | --- |\n'
        for row in rows:
            answer += f'| [{row["key"]}]({row["url"]}) | {cell(row["summary"])} | {cell(row["status"])} | {row["due_label"]} |\n'
        if search.get('isLast') is False or search.get('nextPageToken') or len(search['issues']) > 10:
            answer += '\nShowing the first 10 matching issues; more results are available.'
        if any(not row['due_date_returned'] for row in rows):
            answer += '\nSome due-date fields were not returned by Jira; those dates remain unknown.'
        return outcome(answer, issues=rows)
    except ValueError:
        return outcome('Jira could not complete the assignee issue search. See the tool evidence for the failed read.', ResultStatus.INSUFFICIENT_EVIDENCE)


def active_sprint_request(question):
    text = normalized(question)
    return bool(re.search(rx.JIRA_SPRINT, text)
                and (re.search(rx.JIRA_ACTIVE, text) or re.search(rx.JIRA_IN_SPRINT, text))
                and not re.search(rx.JIRA_WORK_DETAIL, text))


def configured_cloud(resources, config):
    site = config.get('context', {}).get('site_url', '').rstrip('/')
    sites = resources.get('resources', []) if isinstance(resources, dict) else resources
    matches = [item for item in (sites or []) if isinstance(item, dict) and item.get('url', '').rstrip('/') == site]
    if len(matches) != 1 or not matches[0].get('cloudId'):
        raise ValueError('Configured Jira site not uniquely available')
    return matches[0]['cloudId']


def sprint_date(value, timezone):
    if not value:
        return 'Not returned by Jira'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(ZoneInfo(timezone))
            return f'{parsed.day} {parsed.strftime("%B %Y, %H:%M %Z")}'
        return f'{parsed.day} {parsed.strftime("%B %Y")} (timezone not returned)'
    except (ValueError, TypeError):
        return 'Invalid date returned by Jira'


async def active_sprints(question, config, execute):
    if not active_sprint_request(question):
        return None
    evidence, rows, failed, partial = [], [], False, False

    async def read(tool, arguments):
        result = await execute(tool, arguments)
        evidence.append(result)
        data = payload(result)
        if result['is_error'] or isinstance(data, dict) and data.get('error'):
            raise ValueError('Jira read failed')
        return data

    def outcome(answer, status=ResultStatus.ANSWERED):
        return {
            'status': status,
            'answer': answer,
            'tools_used': [f'jira:{item["tool"]}' for item in evidence],
            'support': [],
            'results': [],
            'mcp_evidence': evidence,
            'jira_sprints': rows,
            'notices': ['Connected directly to Jira. Sprint state comes from Jira; dates alone do not establish an active sprint.']
        }

    try:
        cloud = configured_cloud(await read('getAccessibleAtlassianResources', {}), config)
        project = config.get('context', {}).get('project_key')
        explicit = re.search(rx.JIRA_PROJECT_FOR, question)
        if explicit: project = explicit[1]
        arguments = {'cloudId': cloud, 'maxResults': 20}
        if project: arguments['projectKeyOrId'] = project
        requested_board = re.search(rx.JIRA_BOARD, question, re.I)
        board_data = await read('listJiraBoards', arguments)
        boards = board_data.get('values', board_data.get('boards')) if isinstance(board_data, dict) else board_data
        if not isinstance(boards, list):
            return outcome('Jira did not return a usable board list.', ResultStatus.INSUFFICIENT_EVIDENCE)
        partial = isinstance(board_data, dict) and (board_data.get('isLast') is False or bool(board_data.get('nextPageToken')))
        if requested_board:
            boards = [board for board in boards if str(board.get('id')) == requested_board[1]]
            if not boards:
                return outcome('That board was not found in the returned project boards.', ResultStatus.INSUFFICIENT_EVIDENCE)
        scrum = [board for board in boards if normalized(board.get('type', '')) != 'kanban']
        partial = partial or len(scrum) > 10
        for board in scrum[:10]:
            board_id = board.get('id')
            if not isinstance(board_id, int) or isinstance(board_id, bool) or board_id < 1:
                failed = True
                continue
            try:
                sprints = await read('listJiraBoardSprints', {
                    'cloudId': cloud,
                    'boardId': board_id,
                    'state': 'active',
                    'maxResults': 20
                })
            except ValueError:
                failed = True
                continue
            values = sprints.get('values', sprints.get('sprints')) if isinstance(sprints, dict) else sprints
            if not isinstance(values, list):
                failed = True
                continue
            partial = partial or isinstance(sprints, dict) and (sprints.get('isLast') is False or bool(sprints.get('nextPageToken')))
            for sprint in values:
                if not isinstance(sprint, dict) or normalized(sprint.get('state', '')) != 'active' or not sprint.get('id'):
                    failed = True
                    continue
                existing = next((row for row in rows if row['id'] == sprint['id']), None)
                if existing:
                    existing['boards'].append(board.get('name', str(board_id)))
                else:
                    rows.append({
                        **sprint,
                        'boards': [board.get('name', str(board_id))],
                        'board_id': board_id
                    })
        label = cell(project or 'the accessible project boards')
        if not rows:
            if failed or partial:
                return outcome('I could not verify an active sprint: some board reads failed or the results were incomplete.', ResultStatus.INSUFFICIENT_EVIDENCE)
            return outcome(f'No active sprint was returned for {label}.')
        timezone = config.get('context', {}).get('timezone', 'UTC')
        answer = f'Active sprint{ "s" if len(rows) != 1 else "" } in {label}:\n\n'
        for row in rows:
            answer += f'**{cell(row.get("name", str(row["id"])))}** · {cell(", ".join(row["boards"]))}\n\n'
            answer += f'- Start: {sprint_date(row.get("startDate"), timezone)}\n'
            answer += f'- End: {sprint_date(row.get("endDate"), timezone)}\n'
            if row.get('goal'): answer += f'- Goal: {cell(row["goal"])}\n'
            site = config['context']['site_url'].rstrip('/')
            answer += f'- [Open Jira board]({site}/jira/software/projects/{project}/boards/{row["board_id"]})\n\n' if project else ''
        if failed or partial:
            answer += 'Some boards or sprint results were unavailable or incomplete; this list may be partial.'
        return outcome(answer)
    except ValueError:
        return outcome('Jira could not complete the active sprint lookup. See the tool evidence for the failed read.', ResultStatus.INSUFFICIENT_EVIDENCE)


async def issue_details(question, config, execute):
    keys = list(dict.fromkeys(key.upper() for key in re.findall(rx.JIRA_ISSUE_KEY_REFERENCE, question)))
    if len(keys) != 1 or re.search(rx.JIRA_RELATED_ISSUE_REQUEST, question, re.I):
        return None
    if not re.search(rx.JIRA_ISSUE_DETAIL, question, re.I) and question.strip().upper() != keys[0]:
        return None
    evidence = []
    async def read(tool, arguments):
        result = await execute(tool, arguments)
        evidence.append(result)
        data = payload(result)
        if result['is_error'] or isinstance(data, dict) and data.get('error'):
            raise ValueError('Jira read failed')
        return data
    def outcome(answer, status=ResultStatus.ANSWERED):
        return {
            'status': status,
            'answer': answer,
            'tools_used': [f'jira:{item["tool"]}' for item in evidence],
            'support': [],
            'results': [],
            'mcp_evidence': evidence,
            'notices': ['Connected directly to Jira.']
        }
    try:
        cloud = configured_cloud(await read('getAccessibleAtlassianResources', {}), config)
        issue = await read('getJiraIssue', {
            'cloudId': cloud,
            'issueIdOrKey': keys[0],
            'view': 'full',
            'fields': [
                'summary',
                'status',
                'duedate',
                'assignee'
            ]
        })
        if not isinstance(issue, dict) or issue.get('key') != keys[0] or not isinstance(issue.get('fields'), dict):
            return outcome(
                'Jira did not return verified details for that issue.',
                ResultStatus.INSUFFICIENT_EVIDENCE
            )
        fields = issue['fields']
        site = config['context']['site_url'].rstrip('/')
        answer = f'[{keys[0]}]({site}/browse/{keys[0]}): **{cell(fields.get("summary", "Summary not returned"))}**\n\n'
        answer += f'- Status: {cell((fields.get("status") or {}).get("name", "Not returned by Jira"))}\n'
        answer += f'- Assignee: {cell((fields.get("assignee") or {}).get("displayName", "Not returned by Jira"))}\n'
        answer += f'- Due date: **{due_label(fields)}**'
        return outcome(answer)
    except ValueError:
        return outcome(
            'Jira could not read that issue. See the tool evidence for the failed read.',
            ResultStatus.INSUFFICIENT_EVIDENCE
        )
