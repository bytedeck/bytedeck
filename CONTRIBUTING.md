# Contributing

## Quick Reference Guide to Making Code Contributions

If you're interested in contributing to this repo, please work through these steps carefully.  Bad pull requests waste a lot of time, and these steps will ensure your PR is a good one!  This guide is written with beginners in mind, but we would appreciate if experienced developers work through this at least once so we're all on the same page!

Save us all some time and frustration by working through these steps carefully, at least once, and understand them all!

### Running Tests and Checking Code Style
You can run tests either locally, or through the web container:
1. This will run all the project's tests and if successful, will also check the code style using flake8 (make sure you're in your virtual environment):
   * using venv: `python src/manage.py test src && flake8 src`
   * using docker: `docker-compose exec web bash -c "python src/manage.py test src && flake8 src"`  (assuming it's running. If not, change `exec` to `run`)
1. Tests take too long, but you can speed them up a number of ways:
   * Quit after the first error or failure, and also by running th tests in parallel to take advantage of multi-core processors:
     `python src/manage.py test src --parallel --failfast`
   * Only run tests from a single app, for example: `python src/manage.py test src/announcements`
   * Only run tests from a single test class: `python src/manage.py test src.announcements.tests.test_views.AnnouncementViewTests`
   * Only run a single test: `python src/manage.py test src.announcements.tests.test_views.AnnouncementViewTests.test_teachers_have_archive_button`
1. This project uses git pre-commit hooks, set up with the Python "[pre-commit](https://pre-commit.com/)" module. These hooks trigger a series of checks every time a new commit is made. They ensure that the code is formatted correctly, and some even auto-correct certain simple issues. However, we don't have pre-commit hooks for running our Django tests, so the full test suite must still be ran separately. All pre-commit hooks are defined in the [.pre-commit-config.yaml](.pre-commit-config.yaml) file. Note that if auto-corrections are made, the commit won't complete, and you'll need to run the commit command again. It can also be helpful to run these hooks manually to ensure you have everything setup correctly:

   * using venv: `pre-commit run`
   * using docker: `docker-compose exec web bash -c "pre-commit run"`

   Note: Running pre-commit hooks manually is generally used for troubleshooting or setup verification, and is not a required step in the normal development workflow.
### Further Development
After you've got everything set up, you can just run the whole project with:
`docker-compose up`

And stop it with:
`docker-compose down`

or to run in a local venv (assuming you have activated it), start all the docker services in the background (-d) except web, then run the django server locally:
1. `docker-compose up -d db redis celery celery-beat -d`
1. `python src/manage.py runserver`

### First time only:

1. Move into your cloned directory. For example: `cd ~/Developer/bytedeck`
1. Add the upstream remote (if it doesn't already exist): `git remote add upstream git@github.com:bytedeck/bytedeck.git`

### Recurring steps with each PR:

1. Pull in changes from the upstream master: `git pull upstream develop` (in case anything has changed since you cloned it)
1. Create a new branch with a name specific to the issue or feature or bug you will be working on: `git checkout -b yourbranchname`
1. Write tests! See Test Requirements below for important details (if you are not comfortable with test-driven development, you can also write tests after writing code instead of before).  Also see "Running Tests and Checking Code Style" section.
1. Write code!
1. Before committing, make sure to run tests and linting locally (this will save you the annoyance of having to clean up lots of little "oops typo!" commits).  Note that the `--failfast` and `--parallel` modes are optional and used to speed up the tests.  `--failfast` will quit as soon as one test fails, and `--parallel` will run tests in multiple processes (however if a test fails, the output might not be helpful, and you might need to run the tests again without this option to get more info on the failing test):
   * venv: `python src/manage.py test src --failfast --parallel && flake8 src`
   * docker: `docker-compose exec web bash -c "python src/manage.py test src --failfast --parallel && flake8 src"`
1. Commit your changes and provide a [good commit message](https://www.freecodecamp.org/news/how-to-write-better-git-commit-messages/) (you may need to `git add .` if you created any new files that need to be tracked).  If your changes resolve a specific [issue on github](https://github.com/bytedeck/bytedeck/issues), then add "Closes #123" to the commit where 123 is the issue number. Note that if your development environment is running inside of docker and not a Python virtual environment, the pre-commit hooks won't run properly. For this reason, you will be required to run your commit command inside of docker:
   - venv: `git commit -am "Useful description of your changes; Closes #123"`
   - docker: `docker-compose exec web bash -c "git commit -m 'Useful description of your changes; Closes #123'"` (ensure the commit message is enclosed in single and not double quotes)
1. Repeat steps 4-9 above until the feature/issue is completed.
1. If you make mistakes during the commit process, or want to change or edit commits, [here's a great guide](http://sethrobertson.github.io/GitFixUm/fixup.html).
1. Make sure your develop branch is up to date again and rebase onto any changes that have been made upstream since you started the branch: `git pull upstream develop --rebase`  (this command joins several steps: updating your local develop branch, and then rebasing your current feature branch on top of the updated develop branch)
1. You may need to resolve merge conflicts, if there are any. Hopefully not!  ([how to resolve a merge conflict](https://www.youtube.com/watch?v=QmKdodJU-js))
1. Run entire test suite and check coverage (see "Detailed Expectations for all Pull Requests" section below)
1. Push your branch to your fork of the project on github (the first time you do this, it will create the branch on github for you): `git push origin yourbranchname`
1. Go to your fork of the repository on GitHub (you should see a dropdown allowing you to select your branch)
1. Select your recently pushed branch and create a pull request (you should see a button for this)
![image](https://user-images.githubusercontent.com/10604391/125674000-d02eb7a0-b85d-4c8f-b8dd-2b144e274f7d.png)

1. Complete pull request.
1. Once automated tests have finished running on your PR, make sure they passed (they should have, since you already ran the tests locally at step 8... right? RIGHT?!)
1. Engage in the review of your pull request on github (there will likely be some back and forth discussion between you and the maintainer before the PR is accepted)
1. Start work on another feature by checking out the develop branch again: `git checkout develop`
1. Go to Step 4 and repeat!

## Detailed Expectations for all Pull Requests:

### Test Requirements
* New tests should use the naming convention: `def test_method_or_class_name__specific_case_being_tested()`, for example: `test_end_active_semester__staff()` or `test_CourseDelete_view__with_students()`
* All tests must include a useful docstring.  Please use this guide: [How to write docstrings for tests](https://jml.io/test-docstrings/).  If you're curious why our tests need docstrings, see (this article)[https://hynek.me/articles/document-your-tests/].
* All issues labelled "bug" require a test for the bug that **fails** as a result of the bug.  Bug fixing should be test-driven.
* All new server-side code must be 100% tested (all logical branches) unless there is a specific reason it is not feasible. See "Verifying Coverage section below for details.
* When modifying an existing method or class that is not fully tested, at least ensure your additional code is fully tested (this may, incidentally, require you to write additional tests for the existing method/class)
* Front end tests only need to be included in some cases: 1. to confirm the present or absence of key content on a page: For example, a view/template that renders a button that should only be visible by staff users; or 2. to confirm the correction of a bug in the template.

### Verifying Coverage

To verify the test coverage of your additions, you can run coverage during testing; for example, if I made a modification in the Notifications app:
1. Run the notifications tests with coverage:
`docker-compose exec web bash -c "coverage run --source=src ./src/manage.py test src/notifications"`
1. Generate html for the test coverage:
`docker-compose exec web bash -c "coverage html"`
1. View the test coverage by opening `/htmlcov/index.html` in your browser and navigating to your code
1. Confirm that all logical branches of your codes is covered.  Here's an example of missing test coverage:
![image](https://user-images.githubusercontent.com/10604391/209511048-3c3e5035-71d3-4cd3-9c8f-894af9d85475.png)

### Pull Requests

1. Please do not expect your pull request to accept the first time, at least until you are familiar with the project and its expectations.  Expect some requests for clarification (if your code is not well documented) or other minor changes to match the code standards of the project.

1. Except in the most trivial cases, provide a detailed description in your PR that fully details the changes you made, in plain English, and how they address the issue.  The project's expectation is described at https://www.pullrequest.com/blog/writing-a-great-pull-request-description/

### Documentation
Please ensure your code is well documented. Do not assume that your code is obvious to reviewers, other developers, or even your future self:
* All methods and classes must include a docstring that fully explains what the purpose of the function is, why it's needed, and what it's being used for.
* All tests require a docstring (see Test Requirements section for more details).
* All non-trivial code should have a comment describing why it's doing what it's doing.
* If what the code is doing is not immediately obvious, describe what it is doing  (for example, fancy list comprehensions, advanced queryset filters, use of non-standard library methods, etc)
* If you found code on stack overflow, a blog, or elsewhere, link to in within a code comment. This often provides addition context that is helpful to reviewers or future developers.
* Be prepared for requests to add more documentation/comments during review.

## Other considerations when contributing

### Contributing with Multitenant Architecture in Mind:
When contributing to this repo, you need to keep in mind its multi-tenant architecture via [django-tenants](https://django-tenants.readthedocs.io/en/latest/).  Here are a few quick tips:
* **Views**: If you create a new view, class-based views need to use the `NonPublicOnlyViewMixin` and function-based views need the `@non_public_only_view` decorator (see tenants/views.py for definitions for these two).  Unless the view is specifically for the public tenant.
* **Admin**: Model admin classes must all use the `NonPublicSchemaOnlyAdminAccessMixin` unless they are public tenant models.
* **Tests**: Tests that use models need to inherit from the [`TenantTestCase`](https://django-tenants.readthedocs.io/en/latest/test.html#updating-your-app-s-tests-to-work-with-django-tenants) and use the `TenantClient`.
* **SiteConfig**: To get the SiteConfig singleton of a specific tenant, use the class method `SiteConfig.get()`
* **Migrations**: Do NOT use the standard migrate command! If for some reason you need to manually migrate, use the `migrate_schemas` command instead (you can find docs for this and other management commands [here](https://django-tenants.readthedocs.io/en/latest/use.html?highlight=migrations#management-commands))

### Use a Consistent Coding Style
We use Flake8 with [a few exclusions](https://github.com/timberline-secondary/hackerspace/blob/develop/src/.flake8).  These will be enforced by the pre-commit hook.

### Advanced / Optional: Inspecting the database with pgadmin4
Using pgadmin4 we can inspect the postgres database's schemas and tables (helpful for a sanity check sometimes!)
1. Run the pg-admin container:
`docker-compose up pg-admin`
2. Log in:
   - url: [localhost:8080](http://localhost:8080)
   - email: admin@admin.com
   - password: password  (or whatever you changed this to in your `.env` file)
3. Click "Add New Server"
4. Give it any Name you want
5. In the Connection tab set:
   - Host name/address: db
   - Port: 5432
   - Maintenance database: postgres
   - Username: postgres
   - Password: Change.Me!  (or whatever you change the db password to in your `.env` file)
6. Hit Save
7. At the top left expand the Servers tree to find the database, and explore!
8. You'll probably want to look at Schemas > (pick a schema) > Tables

## License
By contributing, you agree that your contributions will be licensed under its [GNU GPL3 License](https://github.com/timberline-secondary/hackerspace/blob/develop/license.txt).
