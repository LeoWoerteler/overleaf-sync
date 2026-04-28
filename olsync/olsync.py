"""Overleaf Two-Way Sync Tool"""
##################################################
# MIT License
##################################################
# File: olsync.py
# Description: Overleaf Two-Way Sync
# Author: Moritz Glöckl
# License: MIT
# Version: 1.2.0
##################################################

import truststore
truststore.inject_into_ssl()

import click
import os
from yaspin import yaspin
import pickle
import zipfile
import io
import dateutil.parser
import glob
import fnmatch
import traceback
from pathlib import Path

try:
    # Import for pip installation / wheel
    from olsync.olclient import OverleafClient
    import olsync.olbrowserlogin as olbrowserlogin
except ImportError:
    # Import for development
    from olclient import OverleafClient
    import olbrowserlogin


@click.group(invoke_without_command=True)
@click.option('-l', '--local-only', 'local', is_flag=True, help="Sync local project files to Overleaf only.")
@click.option('-r', '--remote-only', 'remote', is_flag=True,
              help="Sync remote project files from Overleaf to local file system only.")
@click.option('-n', '--name', 'project_name', default="",
              help="Specify the Overleaf project name instead of the default name of the sync directory.")
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('-p', '--path', 'sync_path', default=".", type=click.Path(exists=True),
              help="Path of the project to sync.")
@click.option('-i', '--olignore', 'olignore_path', default=".olignore", type=click.Path(exists=False),
              help="Path to the .olignore file relative to sync path (ignored if syncing from remote to local). See "
                   "fnmatch / unix filename pattern matching for information on how to use it.")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
@click.option('--server', 'server', default=None,
              help="Overleaf server URL (for private instances). Defaults to the URL saved at login.")
@click.option('--no-verify', 'no_verify', is_flag=True,
              help="Disable SSL certificate verification (use for self-signed certs).")
@click.option('-d', '--dry-run', 'dry_run', is_flag=True,
              help="Show what would be synced without making any changes.")
@click.version_option(package_name='overleaf-sync')
@click.pass_context
def main(ctx, local, remote, project_name, cookie_path, sync_path, olignore_path, verbose, server, no_verify, dry_run):
    if ctx.invoked_subcommand is None:
        if not os.path.isfile(cookie_path):
            raise click.ClickException(
                "Persisted Overleaf cookie not found. Please login or check store path.")

        with open(cookie_path, 'rb') as f:
            store = pickle.load(f)

        overleaf_client = _make_client(store, server, no_verify)

        # Change the current directory to the specified sync path
        os.chdir(sync_path)

        project_name = project_name or Path.cwd().name
        project = execute_action(
            lambda: overleaf_client.get_project(project_name),
            "Querying project",
            "Project queried.",
            "Project could not be queried.",
            verbose)

        zip_file = execute_action(
            lambda: zipfile.ZipFile(io.BytesIO(
                overleaf_client.download_project(project["id"]))),
            "Downloading project",
            "Project downloaded.",
            "Project could not be downloaded.",
            verbose)

        project_infos = execute_action(
            lambda: overleaf_client.get_project_infos(project["id"]),
            "Querying project details",
            "Project details queried.",
            "Project details could not be queried.",
            verbose)

        if verbose:
            if os.path.isfile(olignore_path):
                click.echo(f"\n.olignore: using {olignore_path} to filter items")
            else:
                click.echo("\nNotice: .olignore file does not exist, will sync all items.")

        remote_mtime = dateutil.parser.isoparse(project["lastUpdated"]).timestamp()

        sync_func(
            remote_files=set(zip_file.namelist()),
            local_files=set(olignore_keep_list(olignore_path)),
            content_equal=lambda name: os.path.isfile(name) and Path(name).read_bytes() == zip_file.read(name),
            local_is_newer=lambda name: os.path.getmtime(name) > remote_mtime,
            download=lambda name: write_file(name, zip_file.read(name), mtime=remote_mtime),
            upload=lambda name: overleaf_client.upload_file(project["id"], project_infos, name),
            delete_local=lambda name: delete_file(name),
            delete_remote=lambda name: overleaf_client.delete_file(project["id"], project_infos, name),
            local_only=local,
            remote_only=remote,
            verbose=verbose,
            dry_run=dry_run)


@main.command()
@click.option('--path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Path to store the persisted Overleaf cookie.")
@click.option('--server', 'server', default="https://www.overleaf.com",
              help="Overleaf server URL (for private instances).")
@click.option('--no-verify', 'no_verify', is_flag=True,
              help="Disable SSL certificate verification (use for self-signed certs).")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
def login(cookie_path, server, no_verify, verbose):
    if os.path.isfile(cookie_path) and not click.confirm(
            'Persisted Overleaf cookie already exist. Do you want to override it?'):
        return
    click.clear()
    execute_action(lambda: login_handler(cookie_path, server, no_verify), "Login",
                   f"Cookie persisted as `{click.format_filename(cookie_path)}`.",
                   "Login failed. Please try again.", verbose)


@main.command(name='list')
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('--server', 'server', default=None,
              help="Overleaf server URL (for private instances). Defaults to the URL saved at login.")
@click.option('--no-verify', 'no_verify', is_flag=True,
              help="Disable SSL certificate verification (use for self-signed certs).")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
def list_projects(cookie_path, server, no_verify, verbose):
    def query_projects():
        for index, p in enumerate(sorted(overleaf_client.all_projects(), key=lambda x: x['lastUpdated'], reverse=True)):
            if not index:
                click.echo("\n")
            click.echo(f"{dateutil.parser.isoparse(p['lastUpdated']).strftime('%m/%d/%Y, %H:%M:%S')} - {p['name']}")
        return True

    if not os.path.isfile(cookie_path):
        raise click.ClickException(
            "Persisted Overleaf cookie not found. Please login or check store path.")

    with open(cookie_path, 'rb') as f:
        store = pickle.load(f)

    overleaf_client = _make_client(store, server, no_verify)

    click.clear()
    execute_action(query_projects, "Querying all projects",
                   "Projects listed.",
                   "Querying all projects failed. Please try again.", verbose)


@main.command(name='download')
@click.option('-n', '--name', 'project_name', default="",
              help="Specify the Overleaf project name instead of the default name of the sync directory.")
@click.option('--download-path', 'download_path', default=".", type=click.Path(exists=True))
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('--server', 'server', default=None,
              help="Overleaf server URL (for private instances). Defaults to the URL saved at login.")
@click.option('--no-verify', 'no_verify', is_flag=True,
              help="Disable SSL certificate verification (use for self-signed certs).")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
def download_pdf(project_name, download_path, cookie_path, server, no_verify, verbose):
    def download_project_pdf():
        nonlocal project_name
        project_name = project_name or Path.cwd().name
        project = execute_action(
            lambda: overleaf_client.get_project(project_name),
            "Querying project",
            "Project queried.",
            "Project could not be queried.",
            verbose)

        file_name, content = overleaf_client.download_pdf(project["id"])

        if file_name and content:
            # Change the current directory to the specified sync path
            os.chdir(download_path)
            Path(file_name).write_bytes(content)

        return True

    if not os.path.isfile(cookie_path):
        raise click.ClickException(
            "Persisted Overleaf cookie not found. Please login or check store path.")

    with open(cookie_path, 'rb') as f:
        store = pickle.load(f)

    overleaf_client = _make_client(store, server, no_verify)

    click.clear()

    execute_action(download_project_pdf, "Downloading project's PDF",
                   "PDF downloaded.",
                   "Downloading project's PDF failed. Please try again.", verbose)


def _make_client(store, server, no_verify):
    base_url = server or store.get("server", "https://www.overleaf.com")
    verify = not (no_verify or store.get("no_verify", False))
    return OverleafClient(store["cookie"], store["csrf"], base_url=base_url, verify=verify)


def login_handler(path, base_url="https://www.overleaf.com", no_verify=False):
    store = olbrowserlogin.login(base_url=base_url)
    if store is None:
        return False
    store["server"] = base_url
    store["no_verify"] = no_verify
    with open(path, 'wb+') as f:
        pickle.dump(store, f)
    return True


def delete_file(path):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    if _dir != '' and not os.path.exists(_dir):
        return
    else:
        os.remove(path)


def write_file(path, content, mtime=None):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    # path is a file
    new_dirs = []
    if _dir != '':
        d = _dir
        while d and not os.path.exists(d):
            new_dirs.append(d)
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        if new_dirs:
            os.makedirs(_dir)

    with open(path, 'wb+') as f:
        f.write(content)

    if mtime is not None:
        os.utime(path, (mtime, mtime))
        # Stamp directories after the file write — creating a file inside a
        # directory updates its mtime, so this must come last.
        # Always stamp _dir (the file write touches it even if it pre-existed).
        # Also stamp the pre-existing parent of any newly created dirs, since
        # makedirs touching it updates its mtime too.
        dirs_to_stamp = set(new_dirs)
        if _dir:
            dirs_to_stamp.add(_dir)
        if new_dirs:
            parent_of_new = os.path.dirname(new_dirs[-1])
            if parent_of_new:
                dirs_to_stamp.add(parent_of_new)
        for d in dirs_to_stamp:
            os.utime(d, (mtime, mtime))


def sync_func(remote_files, local_files, content_equal, local_is_newer,
              download, upload, delete_local, delete_remote,
              local_only=False, remote_only=False, verbose=False, dry_run=False):
    if local_only:
        header = "local → remote"
    elif remote_only:
        header = "remote → local"
    else:
        header = "local ↔ remote"

    click.echo(f"\n{'[dry run] ' if dry_run else ''}{header}")

    download_list = []   # remote → local (new or update)
    upload_list = []     # local → remote (new or update)
    prompt_list = []     # (name, side): one-way mode, file only exists on one side
    in_sync = []

    for name in sorted(remote_files | local_files):
        in_remote = name in remote_files
        in_local = name in local_files

        if in_remote and not in_local:
            if local_only:
                prompt_list.append((name, "remote"))
            else:
                download_list.append(name)
        elif in_local and not in_remote:
            if remote_only:
                prompt_list.append((name, "local"))
            else:
                upload_list.append(name)
        else:  # exists on both sides
            if content_equal(name):
                in_sync.append(name)
            elif local_is_newer(name):
                if not remote_only:
                    upload_list.append(name)
            else:
                if not local_only:
                    download_list.append(name)

    # Resolve prompted files interactively (skipped in dry-run)
    delete_local_list = []
    delete_remote_list = []
    if not dry_run:
        for name, side in prompt_list:
            if side == "remote":
                if click.prompt(
                        f'\n-> <{name}> exists on remote but not locally.'
                        f'\n[d]elete from remote or [i]gnore?',
                        default="i", type=click.Choice(['d', 'i'])) == "d":
                    delete_remote_list.append(name)
            else:
                if click.prompt(
                        f'\n-> <{name}> exists locally but not on remote.'
                        f'\n[d]elete locally or [i]gnore?',
                        default="i", type=click.Choice(['d', 'i'])) == "d":
                    delete_local_list.append(name)

    # Print compact plan
    for name in download_list:
        click.echo(f"  ↓  {name}")
    for name in upload_list:
        click.echo(f"  ↑  {name}")
    for name, side in prompt_list:
        if dry_run:
            click.echo(f"  ?  {name}  (only on {side} — will prompt)")
    for name in delete_remote_list:
        click.echo(f"  -  {name}  (deleted from remote)")
    for name in delete_local_list:
        click.echo(f"  -  {name}  (deleted locally)")
    if in_sync:
        click.echo(f"  {len(in_sync)} unchanged")

    # Execute
    if not dry_run:
        for name in download_list:
            try:
                download(name)
            except Exception:
                if verbose:
                    click.echo(traceback.format_exc(), err=True)
                raise click.ClickException(f"Failed to download '{name}'")

        for name in upload_list:
            try:
                upload(name)
            except Exception:
                if verbose:
                    click.echo(traceback.format_exc(), err=True)
                raise click.ClickException(f"Failed to upload '{name}'")

        for name in delete_remote_list:
            try:
                delete_remote(name)
            except Exception:
                if verbose:
                    click.echo(traceback.format_exc(), err=True)
                raise click.ClickException(f"Failed to delete '{name}' from remote")

        for name in delete_local_list:
            try:
                delete_local(name)
            except Exception:
                if verbose:
                    click.echo(traceback.format_exc(), err=True)
                raise click.ClickException(f"Failed to delete '{name}' locally")

    if dry_run:
        click.echo("\n  Dry run complete — no changes were made")


def execute_action(action, progress_message, success_message, fail_message, verbose_error_logging=False):
    with yaspin(text=progress_message, color="green") as spinner:
        try:
            success = action()
        except Exception:
            if verbose_error_logging:
                click.echo(traceback.format_exc(), err=True)
            success = False

        if success:
            spinner.text = success_message
            spinner.ok("✓")
        else:
            spinner.text = fail_message
            spinner.fail("✗")

    if not success:
        raise click.ClickException(fail_message)
    return success



def olignore_keep_list(olignore_path):
    """
    The list of files to keep synced, with support for sub-folders.
    Should only be called when syncing from local to remote.
    """
    files = glob.glob('**', recursive=True)

    if not os.path.isfile(olignore_path):
        keep_list = files
    else:
        with open(olignore_path, 'r') as f:
            ignore_pattern = f.read().splitlines()
        keep_list = [f for f in files if not any(
            fnmatch.fnmatch(f, ignore) for ignore in ignore_pattern)]

    return [Path(item).as_posix() for item in keep_list if not os.path.isdir(item)]


if __name__ == "__main__":
    main()
