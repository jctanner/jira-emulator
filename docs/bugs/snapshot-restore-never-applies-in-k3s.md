# Snapshot restore never takes effect in the k3s image; snapshots omit attachments

## Status: Fixed

## Summary

`POST /api/admin/snapshots/{name}/restore` returned 200, but in the deployed
`jira-emulator:k3s` pod the restored data was never served. The restore
copied the snapshot over the live database with `shutil.copy2`, then ran
`supervisorctl restart jira-api` in the background. That `supervisorctl`
call used the default socket, `/var/run/supervisor.sock`, while
`supervisord.k3s.conf` puts the socket at `/tmp/supervisor.sock`. The call
failed, the API process was never restarted, and it kept serving its
pre-restore view.

Snapshots also held only the database. Attachment rows point at files under
`ATTACHMENT_DIR`, so a restore brought back rows whose files were missing, or
whose `{id}_{filename}` had since been reused by a later upload.

## Reproduction

In the k3s pod: create a snapshot, delete an attachment, restore the
snapshot, then read the issue. The attachment stays gone. The pod log shows
`unix:///var/run/supervisor.sock no such file`.

Found by the Breadboard `rhaistrat-initiative-tests` preflight, markovd run
`markov-run-8fd6432f` (finding P-18; attachments, P-10).

## Fix

- Restore now happens in-process and synchronously. The sqlite3 backup API
  writes the snapshot into the live file, which keeps the WAL consistent.
  The routes then dispose the engine's pool. `DatabaseOperationMiddleware`
  already holds the database lock for admin requests, so nothing else
  touches the database meanwhile. When the call returns, the restored data
  is live; there is no restart to wait for and no dependency on supervisord.
- Each snapshot copies `ATTACHMENT_DIR` to `<snapshot>.db.attachments/`.
  Restore replaces `ATTACHMENT_DIR` from that copy, and delete removes it.
  Snapshots made before this change have no copy; restoring one leaves the
  attachment files alone.
- Tests: `tests/test_snapshots.py`. They cover a restore under an open WAL
  connection, the attachment round trip, legacy snapshots, deleting the
  copy, and an end-to-end REST v2/v3 restore against a file-backed app.
  That last test fails if restore starts a process.
- Verified in the deployed pod by markovd run `markov-run-bd0d2c10`: the
  restore took 0.64 s, an issue created after the snapshot returned 404, and
  the deleted attachment came back with its original content.

## Known remaining behavior

`POST /api/admin/reset` doesn't clear `ATTACHMENT_DIR`. Files from earlier
data stay on disk, and new uploads can overwrite them by name.
