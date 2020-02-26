import requests as rq
import logging
import json
import aiohttp
import time
import asyncio
from zipfile import ZipFile, is_zipfile

API_BASE = "http://localhost:8080/api"
MAX_TIMEOUT = 10
logging.basicConfig(level=logging.INFO)


async def login_session(username, password, email=None) -> aiohttp.ClientSession:
    sess = aiohttp.ClientSession()
    async with sess.post(f'{API_BASE}/auth/session', json={'username': username, 'password': password}) as resp:
        if resp.status != 200:
            logging.error("login failed")
            logging.error(await resp.text())
            sess.close()
            return None
    return sess


def load_user(user='first_admin') -> dict:
    with open(f'user/{user}.json') as f:
        return json.load(f)


async def _submit(sess: aiohttp.ClientSession, lang, problem_id, code=None) -> str:
    '''
    submit `problem_id` with language `lang`
    if `code` is None, use default source decided by `lang`

    Args:
        code: the code path
    '''
    logging.debug('===submission===')
    langs = ['c', 'cpp', 'py']

    # create submission
    async with sess.post(f'{API_BASE}/submission', json={'languageType': lang, 'problemId': problem_id}) as resp:
        rj = await resp.json()
        rc = resp.status
        logging.debug(f"create submission return code:{rc}")
        logging.debug(rj)
        rj = rj['data']
        assert rc == 200

        # open code file
        if code is None:
            # use default
            code = open(f'{langs[lang]}-code.zip', 'rb')
        else:
            # check zip
            if not is_zipfile(code):
                logging.warning('you are submitting a non-zip file.')
            # if it is the path string
            if 'read' not in code:
                code = open(code, 'rb')

        form = aiohttp.FormData(quote_fields=False)
        form.add_field("code", code, content_type="multipart/form-data")
        # upload source
        async with sess.put(f'{API_BASE}/submission/{rj["submissionId"]}', data=form) as resp2:
            status_code = resp2.status
            status_text = await resp2.text()
            logging.debug(status_code)
            logging.debug(status_text)
            assert resp2.status == 200
            logging.debug('===end===')
            return rj["submissionId"]


async def get_status(sess: aiohttp.ClientSession, submissionId: str) -> dict:
    async with sess.get(f"{API_BASE}/submission/{submissionId}") as resp:
        logging.debug("===get_status===")
        context = await resp.json()
        assert resp.status == 200
        context = context["data"]
        logging.debug(f"status:{context}")
        logging.debug("======end ======")
        return {"id": context["submissionId"], "score": context["score"], "status": context["status"], "time": context["timestamp"]}


def get_result(session: aiohttp.ClientSession, submissionIds: list) -> dict:
    loop = asyncio.get_event_loop()
    result = {}
    for submissionId in submissionIds:
        result.update({submissionId: None})
    begin_time = time.time()

    while(True):
        tasks = []
        for submissionId in submissionIds:
            if result[submissionId] == None:
                tasks.append(asyncio.ensure_future(get_status(session, submissionId)))
        loop.run_until_complete(asyncio.wait(tasks))

        for task in tasks:
            res = dict(task.result())
            if res["status"] == -1:
                continue
            submissionId = res["id"]
            res.pop(submissionId)
            result[submissionId] = res

        if time.time() - MAX_TIMEOUT >= begin_time:
            logging.info("time's up")
            result.update({"status":"timeout"})
            return result

        fn_flag = True
        for k in submissionIds:
            if result[k] == None:
                fn_flag = False
                break

        if fn_flag == True:
            break
    return result


if __name__ == "__main__":
    usercfg = load_user()
    loop = asyncio.get_event_loop()
    ses = loop.run_until_complete(login_session(**usercfg))

    times = 25
    tasks = []
    for i in range(times):
        tasks.append(asyncio.ensure_future(_submit(ses, 0, 1)))

    loop.run_until_complete(asyncio.wait(tasks))

    submissionIds = []
    for task in tasks:
        submissionIds.append(task.result())
    result = get_result(ses, submissionIds)
    with open("result.json" , "w") as f:
        f.write(json.dumps(result , indent=4))
