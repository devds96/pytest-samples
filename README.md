# pytest-samples

![Tests](https://github.com/devds96/pytest-samples/actions/workflows/tests.yml/badge.svg)
[![Coverage](https://github.com/devds96/pytest-samples/raw/gh-pages/coverage/coverage_badge.svg)](https://devds96.github.io/pytest-samples/coverage/index.html)
![flake8](https://github.com/devds96/pytest-samples/actions/workflows/lint.yml/badge.svg)
![mypy](https://github.com/devds96/pytest-samples/actions/workflows/type.yml/badge.svg)

A `pytest` plugin to help run only a sample subset of all tests in each
session.

## Introduction

Sometimes, it may not be feasible to run all tests of a project in a
single test session if the tests are time-intensive. Nevertheless, as
long as it is possible to run a few tests with each test session while
ensuring that the different sessions execute different tests, it should
still be possible to get *good* test coverage.

This package is a `pytest` plugin and as the name suggests, it enables
the execution of *samples* of the entire set of tests that `pytest` may
collect. Furthermore, the runtime of the entire test session will be
limited by some *timeout* duration. Once it expires, all remaining tests
will be marked as *skipped*, so that only a certain set of tests will be
run.

See also
[this Stack Overflow question](https://stackoverflow.com/questions/77930045).

## Usage

Currently, there are two modes of operation implemented. In either mode,
the command line flag `--samples-soft-timeout` can be used to set the
timeout after which no further test should be run. The default value for
the timeout can be read from `pytest -h`.

> [!NOTE]<br/>
> Running tests will not be terminated immediately if the timeout
> expires during their execution. Instead, whether the timeout has
> occurred is only checked after each test. This also means that at
> least one test item will always run before the timeout expires.

> [!TIP]<br/>
> To parse the provided string into a `timedelta`, the
> [`pytimeparse`](https://pypi.org/project/pytimeparse/)
> package is used. See its documentation for possible formats.


### Operating in *nostate* mode
As the name suggests, this mode does not record any information
regarding which test have passed, failed etc. In order to nevertheless
allow a different set of tests to be executed with each session, the
list of all tests will be randomly shuffled. This way, the first few
tests run before the timeout expires will most likely be different with
each session. The mode is activated by enabling the plugin with
`--samples=nostate` passed to the `pytest` command line.

> [!CAUTION]<br/>
> The command line flag `--samples-seed` can be used to set the seed of
> the internal random number generator used for shuffling the test items.
> However, this is problematic if the seed is hard-coded since the order
> of tests can then be identical in each session leading to strongly
> reduced coverage. To prevent this from happening, a warning is
> emitted if this flag is provided. This can be deactivated with the
> `--samples-nostate-seeded` flag.

Other flags, such as the flags used for the *stateful* mode described
below, will be ignored by this mode, except for the `--samples-db-path`
path flag. If this flag is provided in stateful mode, the program
terminates with an error.

> [!TIP]<br/>
> The `pytest` plugins
> [`pytest-randomly`](https://pypi.org/project/pytest-randomly/)
> and
> [`pytest-random-order`](https://pypi.org/project/pytest-random-order/)
> also implement random reordering of tests with more control over how
> the tests are actually reordered. If you are only trying to eliminate
> effects introduced by the ordering of the tests, these plugins might
> be better suited. The shuffling implemented here does not make
> considerations regarding the hierarchy of *test modules*, *test*
> *classes* and *test functions* and shuffles all tests at function
> level.

### Operating in *stateful* mode

In stateful mode, activated via `--samples=stateful`, information
regarding **passed**, **xfailed** and **xpassed** tests is written into
an SQLite database file. This information is used to provide a more 
optimized ordering of the tests for each test run. Failed test will not
be recorded since it is assumed that they will be fixed and therefore
changed as soon as possible. The written information is used to
re-schedule tests that have had successful runs after all tests that
were not yet run or have failed. Furthermore, the tests with successful
run will be re-scheduled in order from last to most recent successful
run.

> [!NOTE]<br>
> The database will store the paths of the files containing the tests
> relative to the `pytest` root directory. Changing this directory
> between sessions may therefore invalidate all test items.

> [!NOTE]<br>
> If a test passes, but a fixture it has requested causes an error on
> teardown, that test will not be written to or will be removed from
> the database since it must be assumed that something else might have
> gone wrong.

> [!NOTE]<br>
> The database stores all time information with respect to the UTC
> time zone.

The path to which the database is written must be provided with the
`--samples-db-path` flag. If it is not provided, the program terminates
with an error.

> [!CAUTION]<br/>
> Currently, there is no validation of the actual schema of the database
> in the provided file against the expected schema implemented. If the
> provided path points to a valid SQLite database, additional tables may
> be created or existing ones may get corrupted.

> [!CAUTION]<br/>
> To overwrite the file if it cannot be opened, the
> `--samples-overwrite-broken-db` can be provided. However, this may
> overwrite the provided file path and can lead to data loss.

By default, the results of the session are bulk-written after all tests
have finished or the timeout expires. The recorded "last run" time will
then approximately correspond to the time when the session ended.
Alternatively, the `--samples-write-immediately` flag can be set. Then,
the database will be accessed immediately after the execution of the
individual test item succeeds and the "last run" time will be much
closer to the actual time the test has finished.

There are several flags to modify the ordering of the tests:

- `--samples-randomize`: If this flag is provided, the order of tests
  that are not found in the database and therefore did not have a
  successful execution before will be randomized, similar to what
  happens in *nostate* mode. However, the tests with a
  successful run will still be executed after all tests without a
  successful run in the order from last to most recent time of their
  last successful execution.
- `--samples-seed` can be used to set the seed of the internal random
  number generator used for shuffling the test items, as is the case in
  *nostate* mode. The `--samples-nostate-seeded` is ignored here since
  setting the seed does not necessarily mean that the tests executed in
  each session will be identical due to the information store in the
  database.
- The `--samples-hash-testfiles` flag can be used to enable storing of
  MD5 hashes of the test files in the database alongside. This way,
  changes of the test files can be inferred. If such a change is
  detected, all tests in these files will be dropped from the database
  at the start of the test session since it must be assumed that at
  least one of them has changed. If there was no hash information stored
  in the database from a previous session, but is requested in a later
  session, this will be interpreted as the file having changed, too.
- Once the database has stored all test items, only their last run time
  will be used as a means of determining the test order. To avoid this,
  `--samples-rest-on-saturation` can be set to drop all entries from the
  database once all tests are found in it. Whether all tests have had a
  successful execution is checked both before and after the test run,
  meaning that the database might end up empty after the session.

> [!CAUTION]<br/>
> The algorithm used for hashing the files when
> `--samples-hash-testfiles` is provided is not safe for cryptographical
> application

> [!IMPORTANT]<br/>
> The hashing mechanism provided by `--samples-hash-testfiles` is not
> sufficient to detect *all* changes that may occur to a test function.
> For example, if a test requests a fixture defined in a file that is
> not otherwise tracked, changes to this fixture function will not cause
> all tests depending on it to be dropped from the database.
> Furthermore, although unlikely, hash collisions may obfuscate changes
> made to a test file.

> [!NOTE]<br/>
> The hash produced for the file may depend on the line endings
> (CRLF, LF) used. This must be taken into account when switching
> between systems with differing line endings.

Regardless of whether the `--samples-hash-testfiles` flag is set, all
tests and all files will be removed from the database if they are no
longer collected by `pytest`. This prevents the database from being
cluttered with out-of-date entries. Test entries are removed before each
test run, while files are removed after all test items were executed or
the time has run out. To prevent this cleanup from happening, the flag
`--samples-no-pruning` can be set which will preserve stale entries that
no longer exist. Note that if `--samples-hash-testfiles` is set and a
file changes, the associated test item entries will still be removed.

If you need to debug the plugin, you can set the flag
`--samples-enable-db-logging` to enable `sqlalchemy`'s logging.

## Installation
You can install the latest version of this package directly from GitHub:
```
pip install git+https://github.com/devds96/pytest-samples
```

Alternatively, you can clone the git repo and run in its root directory:
```
pip install .
```

## Future Ideas

Some further ideas that may be implemented in the future:

- Instead of computing the MD5 hash of test files, it may be faster to
  use hash functions provided by packages such as
  [`metrohash`](https://pypi.org/project/metrohash/).
- Instead of using a *soft* timeout method, where whether it has expired
  is only checked after each test, it is possible to use a *hard*
  timeout which *immediately* (with some limitations) terminates the
  tests using the mechanisms implemented in
  [`pytest-timeout`](https://pypi.org/project/pytest-timeout/).
- Currently, it seems to be relatively difficult to perform validations
  of the database schema using `sqlalchemy`. However, this validation
  would be a necessary step to protect erroneously passed database
  files which are SQLite databases but are not the intended target.
  As mentioned above, the default behavior of `sqlalchemy` is to simply
  create the required tables if they are not present.
