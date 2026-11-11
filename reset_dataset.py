"""Explicitly reset the configured portrait dataset, remotely and locally."""
from pathlib import Path
import shutil

from filelock import FileLock
from huggingface_hub import HfApi, CommitOperationDelete, hf_hub_download
from huggingface_hub.errors import RepositoryNotFoundError


LOCAL_ENTRIES = {
    'original', 'transparent', 'prompts', 'parameters', 'uploads', 'img', 'images',
    'session.sqlite3', 'session.sqlite3-wal', 'session.sqlite3-shm', 'session.lock',
}


def reset_dataset(config, config_dir, progress=print):
    """Use the generator lock; retain local records if remote reset fails.

    Reset main's data and history while retaining the dataset card and attributes.
    Refuse other refs: squashing main cannot remove data retained by tags/branches.
    """
    config_dir = Path(config_dir).resolve()
    raw_output = Path(config['generation']['output_dir'])
    output = config_dir / raw_output
    if output.is_symlink():
        raise ValueError('Refusing a symlink dataset directory')
    output = output.resolve()
    source_dir = Path(__file__).resolve().parent
    if output in (config_dir, source_dir) or output in config_dir.parents or output in source_dir.parents:
        raise ValueError('Refusing to reset a source/config directory or its ancestor')
    repo = config.get('huggingface', {}).get('repo_id')
    if not repo:
        raise ValueError('huggingface.repo_id is required to reset both datasets')
    output.mkdir(parents=True, exist_ok=True)
    with FileLock(output / 'session.lock', timeout=0):
        unknown = {path.name for path in output.iterdir()} - LOCAL_ENTRIES
        if unknown:
            raise ValueError(f'Refusing unexpected files in dataset directory: {sorted(unknown)}')
        api = HfApi()
        progress(f'Resetting Hugging Face dataset {repo} using your saved login...')
        try:
            head = api.repo_info(repo, repo_type='dataset').sha
        except RepositoryNotFoundError as error:
            # HF can also hide private repositories behind 404. Do not assume absence
            # and destroy local data unless the server explicitly reports deletion.
            raise RuntimeError('Dataset was not accessible; local data was retained. Check your HF login and repo_id.') from error
        refs = api.list_repo_refs(repo, repo_type='dataset')
        if list(refs.tags) or any(branch.name != 'main' for branch in refs.branches):
            raise ValueError('Dataset has additional branches/tags; remove those data-retaining refs before resetting')
        card = Path(hf_hub_download(repo, 'README.md', repo_type='dataset', revision=head)).read_text(encoding='utf-8')
        if 'live_upload_layout: ds-photo-id-v1' not in card:
            raise ValueError('Refusing to reset a repository without the portrait dataset marker')
        files = api.list_repo_files(repo, repo_type='dataset', revision=head)
        unexpected = [name for name in files if name not in ('README.md', '.gitattributes') and not name.startswith('data/')]
        if unexpected:
            raise ValueError(f'Refusing unexpected remote files: {unexpected}')
        data_files = [name for name in files if name.startswith('data/')]
        for start in range(0, len(data_files), 100):
            group = data_files[start:start + 100]
            api.create_commit(repo, repo_type='dataset', revision='main',
                              operations=[CommitOperationDelete(path_in_repo=name) for name in group],
                              commit_message='Reset generated portrait data', parent_commit=head)
            head = api.repo_info(repo, repo_type='dataset').sha
            progress(f'Removed {start + len(group)}/{len(data_files)} remote files')
        if any(name.startswith('data/') for name in api.list_repo_files(repo, repo_type='dataset')):
            raise RuntimeError('Remote data remains or was uploaded during reset. Stop all generators and retry; local data retained.')
        api.super_squash_history(repo, repo_type='dataset', branch='main',
                                 commit_message='Fresh portrait dataset after reset')
        progress('Hugging Face data cleared and main history squashed; card retained.')
        for path in output.iterdir():
            if path.name == 'session.lock':
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        progress(f'Local images, prompts, parameters, upload staging and session journal cleared: {output}')
        progress('Reset complete. Run the generator normally to start a fresh session.')
