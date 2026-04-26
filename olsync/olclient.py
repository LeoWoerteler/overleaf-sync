"""Overleaf Client"""
##################################################
# MIT License
##################################################
# File: olclient.py
# Description: Overleaf API Wrapper
# Author: Moritz Glöckl
# License: MIT
# Version: 1.2.0
##################################################

import requests as reqs
import urllib3
from bs4 import BeautifulSoup
import json
import mimetypes
PATH_SEP = "/"  # Use hardcoded path separator for both windows and posix system

class OverleafClient(object):
    """
    Overleaf API Wrapper
    Supports login, querying all projects, querying a specific project, downloading a project and
    uploading a file to a project.
    """

    @staticmethod
    def filter_projects(json_content, more_attrs=None):
        more_attrs = more_attrs or {}
        for p in json_content:
            if not p.get("archived") and not p.get("trashed"):
                if all(p.get(k) == v for k, v in more_attrs.items()):
                    yield p

    @staticmethod
    def _extract_projects_from_page(page_content):
        soup = BeautifulSoup(page_content, 'html.parser')
        meta = soup.find('meta', {'name': 'ol-projects'})
        if meta:
            return json.loads(meta.get('content'))
        meta = soup.find('meta', {'name': 'ol-prefetchedProjectsBlob'})
        if meta:
            return json.loads(meta.get('content'))['projects']
        raise AttributeError("Could not find projects metadata in page")

    def __init__(self, cookie=None, csrf=None, base_url="https://www.overleaf.com", verify=True):
        self._cookie = cookie
        self._csrf = csrf
        self._verify = verify
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        base = base_url.rstrip("/")
        self._base_url     = base
        self._login_url    = f"{base}/login"
        self._project_url  = f"{base}/project"
        self._download_url = f"{base}/project/{{}}/download/zip"
        self._upload_url   = f"{base}/project/{{}}/upload"
        self._folder_url   = f"{base}/project/{{}}/folder"
        self._doc_url        = f"{base}/project/{{}}/doc"
        self._delete_doc_url = f"{base}/project/{{}}/doc/{{}}"
        self._delete_file_url = f"{base}/project/{{}}/file/{{}}"
        self._compile_url  = f"{base}/project/{{}}/compile?enable_pdf_caching=true"

    def login(self, username, password):
        """
        WARNING - DEPRECATED - Not working as Overleaf introduced captchas
        Login to the Overleaf Service with a username and a password
        Params: username, password
        Returns: Dict of cookie and CSRF
        """

        get_login = reqs.get(self._login_url, verify=self._verify)
        self._csrf = BeautifulSoup(get_login.content, 'html.parser').find(
            'input', {'name': '_csrf'}).get('value')
        login_json = {
            "_csrf": self._csrf,
            "email": username,
            "password": password
        }
        post_login = reqs.post(self._login_url, json=login_json,
                               cookies=get_login.cookies, verify=self._verify)

        # On a successful authentication the Overleaf API returns a new authenticated cookie.
        # If the cookie is different than the cookie of the GET request the authentication was successful
        if post_login.status_code == 200 and get_login.cookies["overleaf_session2"] != post_login.cookies[
            "overleaf_session2"]:
            self._cookie = post_login.cookies

            # Enrich cookie with GCLB cookie from GET request above
            self._cookie['GCLB'] = get_login.cookies['GCLB']

            # CSRF changes after making the login request, new CSRF token will be on the projects page
            projects_page = reqs.get(self._project_url, cookies=self._cookie, verify=self._verify)
            self._csrf = BeautifulSoup(projects_page.content, 'html.parser').find('meta', {'name': 'ol-csrfToken'}) \
                .get('content')

            return {"cookie": self._cookie, "csrf": self._csrf}

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived and not trashed)
        Returns: List of project objects
        """
        projects_page = reqs.get(self._project_url, cookies=self._cookie, verify=self._verify)
        json_content = OverleafClient._extract_projects_from_page(projects_page.content)
        return list(OverleafClient.filter_projects(json_content))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object
        """

        projects_page = reqs.get(self._project_url, cookies=self._cookie, verify=self._verify)
        json_content = OverleafClient._extract_projects_from_page(projects_page.content)
        return next(OverleafClient.filter_projects(json_content, {"name": project_name}), None)

    def download_project(self, project_id):
        """
        Download project in zip format
        Params: project_id, the id of the project
        Returns: bytes string (zip file)
        """
        r = reqs.get(self._download_url.format(project_id),
                     stream=True, cookies=self._cookie, verify=self._verify)
        return r.content

    def create_folder(self, project_id, parent_folder_id, folder_name):
        """
        Create a new folder in a project

        Params:
        project_id: the id of the project
        parent_folder_id: the id of the parent folder, root is the project_id
        folder_name: how the folder will be named

        Returns: folder id or None
        """

        params = {
            "parent_folder_id": parent_folder_id,
            "name": folder_name
        }
        headers = {
            "X-Csrf-Token": self._csrf
        }
        r = reqs.post(self._folder_url.format(project_id),
                      cookies=self._cookie, headers=headers, json=params, verify=self._verify)

        if r.ok:
            return json.loads(r.content)
        elif r.status_code == 400:
            # Folder already exists
            return
        else:
            raise reqs.HTTPError()

    def _get_project_infos_via_browser(self, project_id):
        """
        Use Qt WebEngine to open the project editor in the background and
        intercept the socket.io joinProject response.  Cookies are injected
        via a QWebEngineUrlRequestInterceptor so they are guaranteed to reach
        the server regardless of how the cookie store is initialised.
        """
        try:
            from PySide6.QtCore import QUrl, QEventLoop, QTimer
            from PySide6.QtWidgets import QApplication
            from PySide6.QtWebEngineCore import (
                QWebEnginePage, QWebEngineProfile, QWebEngineScript,
                QWebEngineUrlRequestInterceptor,
            )
        except ImportError:
            return None

        cookie_header = "; ".join(
            f"{k}={v}" for k, v in self._cookie.items()
        ).encode()

        class _CookieInjector(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info):  # noqa: N802
                info.setHttpHeader(b"Cookie", cookie_header)

        app = QApplication.instance() or QApplication([])
        profile = QWebEngineProfile()
        injector = _CookieInjector(profile)
        profile.setUrlRequestInterceptor(injector)

        intercept_js = r"""
(function () {
  var delim = '\ufffd';

  function findRF(o) {
    if (!o || typeof o !== 'object') return null;
    if (Array.isArray(o)) {
      for (var k = 0; k < o.length; k++) { var r = findRF(o[k]); if (r) return r; }
      return null;
    }
    if (o.rootFolder) return o;
    for (var key in o) { var res = findRF(o[key]); if (res) return res; }
    return null;
  }

  function capture(text) {
    if (!text) return;
    var packets = text.startsWith(delim) ? [] : [text];
    if (packets.length === 0) {
      var s = text;
      while (s) {
        s = s.slice(1);
        var end = s.indexOf(delim);
        if (end < 0) break;
        var len = parseInt(s.slice(0, end), 10);
        packets.push(s.slice(end + 1, end + 1 + len));
        s = s.slice(end + 1 + len);
      }
    }
    packets.forEach(function (p) {
      /* Socket.IO v0 packet: TYPE:ID:ENDPOINT:DATA
         JS split(sep, limit) discards the tail, so reconstruct data manually. */
      var colonParts = p.split(':');
      if (colonParts.length < 4) return;
      var type = colonParts[0];
      var data = colonParts.slice(3).join(':');

      /* socket.io ack (type 6) — some server versions */
      if (type === '6' && data.startsWith('1+')) {
        try {
          var args = JSON.parse(data.slice(2));
          if (Array.isArray(args)) {
            for (var i = 0; i < args.length; i++) {
              var found = findRF(args[i]);
              if (found) { window._ols_project_infos = JSON.stringify(found); break; }
            }
          }
        } catch (e) {}
      }

      /* joinProjectResponse event (type 5) — this server's pattern */
      if (type === '5') {
        try {
          var ev = JSON.parse(data);
          if (ev.name === 'joinProjectResponse' && Array.isArray(ev.args)) {
            for (var j = 0; j < ev.args.length; j++) {
              var found = findRF(ev.args[j]);
              if (found) { window._ols_project_infos = JSON.stringify(found); break; }
            }
          }
        } catch (e) {}
      }
    });
  }

  /* Intercept WebSocket transport via Proxy (survives security restrictions) */
  if (typeof WebSocket !== 'undefined' && typeof Proxy !== 'undefined') {
    window.WebSocket = new Proxy(WebSocket, {
      construct: function (Target, args) {
        var ws = new Target(...args);
        ws.addEventListener('message', function (e) { capture(e.data); });
        return ws;
      }
    });
  }
})();
"""
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(intercept_js)
        profile.scripts().insert(script)

        page = QWebEnginePage(profile)
        loop = QEventLoop()
        result = [None]
        poll_timer = QTimer()
        deadline_timer = QTimer()

        def _poll():
            page.runJavaScript('window._ols_project_infos || null', _got)

        def _got(v):
            if v is not None:
                try:
                    result[0] = json.loads(v)
                except Exception:
                    pass
                _done()

        def _done():
            poll_timer.stop()
            deadline_timer.stop()
            loop.quit()

        def _on_load(ok):
            if not ok:
                _done()
                return
            # Bail out early if the server redirected us to the login page.
            def _check_url(url):
                if url and '/login' in url:
                    _done()
            page.runJavaScript("window.location.pathname", _check_url)
            poll_timer.timeout.connect(_poll)
            poll_timer.start(500)
            deadline_timer.setSingleShot(True)
            deadline_timer.timeout.connect(_done)
            deadline_timer.start(30_000)

        page.loadFinished.connect(_on_load)
        page.load(QUrl(f"{self._project_url}/{project_id}"))
        loop.exec()

        # Keep references alive until Qt has cleaned up.
        del page, injector, profile
        return result[0]

    def get_project_infos(self, project_id):
        """
        Get detailed project infos about the project

        Params:
        project_id: the id of the project

        Returns: project details
        """
        infos = self._get_project_infos_via_browser(project_id)
        if infos is not None:
            return infos
        raise RuntimeError(f"Could not retrieve project info for {project_id}")

    def _resolve_folder(self, project_id, project_infos, file_name):
        """Navigate (and create if needed) the folder path for file_name.
        Returns (folder_id, base_name)."""
        folder_id = project_infos['rootFolder'][0]['_id']
        parts = file_name.split(PATH_SEP)
        if len(parts) == 1:
            return folder_id, file_name
        current_folders = project_infos['rootFolder'][0]['folders']
        for folder_name in parts[:-1]:
            match = next(
                (f for f in current_folders if f['name'].lower() == folder_name.lower()),
                None,
            )
            if match:
                folder_id = match['_id']
                current_folders = match['folders']
            else:
                new_folder = self.create_folder(project_id, folder_id, folder_name)
                current_folders.append(new_folder)
                folder_id = new_folder['_id']
                current_folders = new_folder['folders']
        return folder_id, parts[-1]

    def upload_file(self, project_id, project_infos, file_name, file_size, file):
        """
        Upload a file to the project.

        Params:
        project_id: the id of the project
        file_name: how the file will be named (may include path separators)
        file_size: the size of the file in bytes
        file: the file object (opened in binary mode)

        Returns: True on success
        """
        folder_id, base_name = self._resolve_folder(project_id, project_infos, file_name)

        mime_type = mimetypes.guess_type(base_name)[0] or "application/octet-stream"
        headers = {"X-CSRF-TOKEN": self._csrf}
        r = reqs.post(
            self._upload_url.format(project_id),
            cookies=self._cookie,
            headers=headers,
            params={"folder_id": folder_id},
            data={"relativePath": "null", "name": base_name, "type": mime_type},
            files={"qqfile": (base_name, file, mime_type)},
            verify=self._verify,
        )
        r.raise_for_status()
        if not r.json().get("success"):
            raise reqs.HTTPError(f"Upload of '{file_name}' rejected by server")
        return True

    def delete_file(self, project_id, project_infos, file_name):
        """
        Deletes a project's file

        Params:
        project_id: the id of the project
        file_name: how the file will be named

        Returns: True on success, False on fail
        """

        base_name = file_name.split(PATH_SEP)[-1]

        # Navigate to the containing folder
        if PATH_SEP in file_name:
            folder = project_infos['rootFolder'][0]
            for part in file_name.split(PATH_SEP)[:-1]:
                folder = next(
                    (f for f in folder['folders'] if f['name'].lower() == part.lower()),
                    None,
                )
                if folder is None:
                    raise RuntimeError(f"Folder not found in project tree while deleting '{file_name}'")
        else:
            folder = project_infos['rootFolder'][0]

        # Look in docs (text) first, then binary file refs.
        # Older ShareLaTeX versions use 'fileRefs' instead of 'files'.
        entry = next((v for v in folder.get('docs', []) if v['name'] == base_name), None)
        if entry is not None:
            delete_url = self._delete_doc_url.format(project_id, entry['_id'])
        else:
            binary = folder.get('fileRefs', folder.get('files', []))
            entry = next((v for v in binary if v['name'] == base_name), None)
            if entry is None:
                raise RuntimeError(
                    f"'{file_name}' not found in project tree "
                    f"(docs={[d['name'] for d in folder.get('docs', [])]} "
                    f"files={[f['name'] for f in folder.get('files', folder.get('fileRefs', []))]})"
                )
            delete_url = self._delete_file_url.format(project_id, entry['_id'])

        headers = {"X-Csrf-Token": self._csrf}
        r = reqs.delete(delete_url, cookies=self._cookie, headers=headers,
                        allow_redirects=False, verify=self._verify)
        if r.is_redirect:
            raise reqs.HTTPError(
                f"Delete of '{file_name}' was redirected to {r.headers.get('Location')!r} "
                f"— session or CSRF token may be invalid; try logging in again"
            )
        r.raise_for_status()
        return True

    def download_pdf(self, project_id):
        """
        Compiles and returns a project's PDF

        Params:
        project_id: the id of the project

        Returns: PDF file name and content on success
        """
        headers = {
            "X-Csrf-Token": self._csrf
        }

        body = {
            "check": "silent",
            "draft": False,
            "incrementalCompilesEnabled": True,
            "rootDoc_id": "",
            "stopOnFirstError": False
        }

        r = reqs.post(self._compile_url.format(project_id), cookies=self._cookie, headers=headers, json=body, verify=self._verify)

        if not r.ok:
            raise reqs.HTTPError()

        compile_result = json.loads(r.content)

        if compile_result["status"] != "success":
            raise reqs.HTTPError()

        pdf_file = next(v for v in compile_result['outputFiles'] if v['type'] == 'pdf')

        download_req = reqs.get(self._base_url + pdf_file['url'], cookies=self._cookie, headers=headers, verify=self._verify)

        if download_req.ok:
            return pdf_file['path'], download_req.content

        return None
