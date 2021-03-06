import os
import sys
import shutil
import subprocess

excluded_objects = ['utf8proc_data.cpp']

def get_libraries(binary_dir, libraries):
    result_libs = []
    def find_library_recursive(search_dir, potential_libnames):
        flist = os.listdir(search_dir)
        for fname in flist:
            fpath = os.path.join(search_dir, fname)
            if os.path.isdir(fpath):
                entry = find_library_recursive(fpath, potential_libnames)
                if entry != None:
                    return entry
            elif os.path.isfile(fpath) and fname in potential_libnames:
                return search_dir
        return None

    def find_library(search_dir, libname, result_libs):
        if libname == 'Threads::Threads':
            result_libs += [(None, 'pthread')]
            return
        libextensions = ['.a', '.lib']
        libprefixes = ['', 'lib']
        potential_libnames = []
        for ext in libextensions:
            for prefix in libprefixes:
                potential_libnames.append(prefix + libname + ext)
        libdir = find_library_recursive(binary_dir, potential_libnames)

        result_libs += [(libdir, libname)]

    result_libs += [(os.path.join(binary_dir, 'src'), 'duckdb_static')]
    result_libs += [(os.path.join(binary_dir, 'extension', 'parquet'), 'parquet_extension')]
    result_libs += [(os.path.join(binary_dir, 'extension', 'icu'), 'icu_extension')]

    for libname in libraries:
        find_library(binary_dir, libname, result_libs)

    return result_libs

def includes():
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    # add includes for duckdb and parquet
    includes = []
    includes.append(os.path.join(scripts_dir, '..', 'src', 'include'))
    includes.append(os.path.join(scripts_dir, '..', 'extension', 'parquet', 'include'))
    return includes

def include_flags():
    return ' ' + ' '.join(['-I' + x for x in includes()])

def convert_backslashes(x):
    return '/'.join(x.split(os.path.sep))

def get_relative_path(source_dir, target_file):
    source_dir = convert_backslashes(source_dir)
    target_file = convert_backslashes(target_file)

    # absolute path: try to convert
    if source_dir in target_file:
        target_file = target_file.replace(source_dir, "").lstrip('/')
    return target_file

def build_package(target_dir, linenumbers = False):
    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(scripts_dir)
    import amalgamation
    sys.path.append(os.path.join(scripts_dir, '..', 'extension', 'parquet'))
    import parquet_amalgamation

    prev_wd = os.getcwd()
    os.chdir(os.path.join(scripts_dir, '..'))

    # obtain the list of source files from the amalgamation
    source_list = amalgamation.list_sources()
    include_list = amalgamation.list_include_dirs()
    include_files = amalgamation.list_includes()

    def copy_file(src, target_dir):
        # get the path
        full_path = src.split(os.path.sep)
        current_path = target_dir
        for i in range(len(full_path) - 1):
            current_path = os.path.join(current_path, full_path[i])
            if not os.path.isdir(current_path):
                os.mkdir(current_path)
        target_name = full_path[-1]
        target_file = os.path.join(current_path, target_name)
        amalgamation.copy_if_different(src, target_file)


    # now do the same for the parquet extension
    parquet_include_directories = parquet_amalgamation.include_directories

    include_files += amalgamation.list_includes_files(parquet_include_directories)

    include_list += parquet_include_directories
    source_list += parquet_amalgamation.source_files

    for src in source_list:
        copy_file(src, target_dir)

    for inc in include_files:
        copy_file(inc, target_dir)

    # handle pragma_version.cpp: paste #define DUCKDB_SOURCE_ID there
    # read the source id
    proc = subprocess.Popen(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.path.join(scripts_dir, '..'))
    githash = proc.stdout.read().strip().decode('utf8')
    # open the file and read the current contents
    fpath = os.path.join(target_dir, 'src', 'function', 'table', 'version', 'pragma_version.cpp')
    with open(fpath, 'r') as f:
        text = f.read()
    # now add the DUCKDB_SOURCE_ID define, if it is not there already
    found = False
    lines = text.split('\n')
    for i in range(len(lines)):
        if '#define DUCKDB_SOURCE_ID ' in lines[i]:
            lines[i] = '#define DUCKDB_SOURCE_ID "{}"'.format(githash)
            found = True
            break
    if not found:
        text = '#ifndef DUCKDB_SOURCE_ID\n#define DUCKDB_SOURCE_ID "{}"\n#endif\n'.format(githash) + text
    else:
        text = '\n'.join(text)
    with open(fpath, 'w+') as f:
        f.write(text)

    def file_is_excluded(fname):
        for entry in excluded_objects:
            if entry in fname:
                return True
        return False

    def generate_unity_build(entries, idx, linenumbers):
        ub_file = os.path.join(target_dir, 'amalgamation-{}.cpp'.format(str(idx)))
        with open(ub_file, 'w+') as f:
            for entry in entries:
                if linenumbers:
                    f.write('#line 0 "{}"\n'.format(convert_backslashes(entry)))
                f.write('#include "{}"\n\n'.format(convert_backslashes(entry)))
        return ub_file

    def generate_unity_builds(source_list, nsplits, linenumbers):
        source_list.sort()

        files_per_split = len(source_list) / nsplits
        new_source_files = []
        current_files = []
        idx = 1
        for entry in source_list:
            if not entry.startswith('src'):
                new_source_files.append(os.path.join('duckdb', entry))
                continue

            current_files.append(entry)
            if len(current_files) > files_per_split:
                new_source_files.append(generate_unity_build(current_files, idx, linenumbers))
                current_files = []
                idx += 1
        if len(current_files) > 0:
            new_source_files.append(generate_unity_build(current_files, idx, linenumbers))
            current_files = []
            idx += 1

        return new_source_files

    original_sources = source_list
    source_list = generate_unity_builds(source_list, 8, linenumbers)

    os.chdir(prev_wd)
    return ([convert_backslashes(x) for x in source_list if not file_is_excluded(x)],
            [convert_backslashes(x) for x in include_list],
            [convert_backslashes(x) for x in original_sources])
