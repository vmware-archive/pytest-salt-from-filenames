# -*- coding: utf-8 -*-

# Import Python libs
from __future__ import absolute_import, unicode_literals, print_function
import os
import re


def _inject_test_modules(test_module_paths, args):
    # modules into args
    for path in test_module_paths:
        if path not in args:
            args.append(path)


def pytest_addoption(parser):
    group = parser.getgroup('Tests Selection')
    group.addoption(
        '--from-filenames',
        default=None,
        help=('Pass a comma-separated list of file paths, and any '
              'unit/integration test module which corresponds to the '
              'specified file(s) will be run. For example, a path of '
              'salt/modules/git.py would result in unit.modules.test_git '
              'and integration.modules.test_git being run. Absolute paths '
              'are assumed to be files containing relative paths, one per '
              'line. Providing the paths in a file can help get around '
              'shell character limits when the list of files is long.')
    )



def pytest_load_initial_conftests(early_config, args):
    from_filenames_idx = None
    from_filenames_equals_idx = None
    for idx, arg in enumerate(args):
        if arg.startswith('--from-filenames='):
            from_filenames_equals_idx = idx
            break
        elif arg.startswith('--from-filenames'):
            from_filenames_idx = idx
            break

    if from_filenames_idx is None and from_filenames_equals_idx is None:
        # There's nothing for us to do
        return

    if from_filenames_idx is not None:
        args.pop(from_filenames_idx)
        from_filenames_str = args.pop(from_filenames_idx)
    elif from_filenames_equals_idx:
        from_filenames_str = args.pop(from_filenames_equals_idx).split('--from-filenames=', 1)[-1]

    test_module_paths = []
    from_filenames = []
    for path in [path.strip() for path in from_filenames_str.split(',')]:
        if not os.path.exists(os.path.join(early_config.rootdir, path)):
            # This path does not map to any file in salt's source tree
            continue
        if path in from_filenames:
            # No duplicates please
            continue

        if os.path.basename(path).startswith('test_'):
            test_module_paths.append(path)
        else:
            from_filenames.append(path)

    matcher = re.compile(r'^(salt/|tests/(integration|unit)/)(.+\.py)$')

    def _add(comps):
        '''
        Helper to add unit and integration tests matching a given mod path
        '''
        mod_relname = os.path.join(*comps)
        for test_type in ('unit', 'integration'):
            test_module_path = os.path.join('tests', test_type, mod_relname)
            if os.path.exists(test_module_path):
                if test_module_path not in test_module_paths:
                    test_module_paths.append(test_module_path)


    # First, try a path match
    for path in from_filenames:
        match = matcher.match(path)
        if match:
            comps = match.group(3).split(os.sep)
            if len(comps) < 2:
                continue

            # Find matches for a source file
            if match.group(1) == 'salt/':
                if comps[-1] == '__init__.py':
                    comps.pop(-1)
                comps[-1] = 'test_{}'.format(comps[-1])

                # Direct name matches
                _add(comps)

                # State matches for execution modules of the same name
                # (e.g. unit.states.test_archive if
                # unit.modules.test_archive is being run)
                try:
                    if comps[-2] == 'modules':
                        comps[-2] = 'states'
                        _add(comps)
                except IndexError:
                    # Not an execution module. This is either directly in
                    # the salt/ directory, or salt/something/__init__.py
                    pass

            # Make sure to run a test module if it's been modified
            elif match.group(1).startswith('tests/'):
                # We should have taken care of these already
                continue

    # Next, try the filename_map
    salt_filename_map = os.path.join(early_config.rootdir, 'tests', 'filename_map.yml')
    if not os.path.exists(salt_filename_map):
        # We can't map salt modules to test modules
        # Inject any passed in test modules into args
        _inject_test_modules(test_module_paths, args)
        return

    # Late import, we're actually importing from Salt
    try:
        import salt.utils.files
        import salt.utils.yaml
        import salt.utils.stringutils
        with salt.utils.files.fopen(salt_filename_map) as fp_:
            filename_map = salt.utils.yaml.safe_load(fp_)
        for path_expr in filename_map:
            for filename in from_filenames:
                if not salt.utils.stringutils.expr_match(filename, path_expr):
                    continue
                for mod in filename_map[path_expr]:
                    test_module_path = os.path.join('tests', mod.replace('.', os.sep) + '.py')
                    if os.path.exists(test_module_path):
                        if test_module_path not in test_module_paths:
                            test_module_paths.append(test_module_path)
    except ImportError:
        pass

    # Inject any passed in test modules into args
    _inject_test_modules(test_module_paths, args)
