# Contributing

## Quick Reference Guide to Making Code Contributions

If you're interested in contributing to this repo, please work through these steps carefully.  Bad pull requests waste a lot of time, and these steps will ensure your PR is a good one!  This guide is written with beginngers in mind, but we would appreciate if experienced developers work through this at least once so we're all on the same page!

### First time only:

1. Move into your cloned directory. For example: `cd ~/Developer/bytedeck`
2. Initialize pre-commit hooks: `git init --template=.git-template && chmod +x .git/hooks/pre-commit`
3. Add the upstream remote (if it doesn't already exist): `git remote add upstream git@github.com:bytedeck/bytedeck.git`

### Recurring steps with each PR:

4. Pull in changes from the upstream master: `git pull upstream develop` (in case anything has changed since you cloned it)
5. Create a new branch with a name specific to the issue or feature or bug you will be working on: `git checkout -b yourbranchname`
6. Write code!
7. Before committing, make sure to run tests and linting locally (this will save you the annoyance of having to clean up lots of little "oops typo!" commits).  Note that the `--failfast` and `--parallel` modes are optional and used to speed up the tests.  `--failfast` will quit as soon as one test fails, and `--parallel` will run tests in multiple processes (however if a test fails, the output might not be helpful, and you might need to run the tests again without this option to get more info on the failing test):   
`./src/manage.py test src --failfast --parallel && flake8 src`
8. Commit your changes and provide a [good commit message](https://www.freecodecamp.org/news/how-to-write-better-git-commit-messages/) (you may need to `git add .` if you created any new files that need to be tracked).  If your changes resolve a specific [issue on github](https://github.com/bytedeck/bytedeck/issues), then add "Closes #123" to the commit where 123 is the issue number:  
`git commit -am "Useful description of your changes; Closes #123"`
8. If you make mistakes during the commit process, or want to change or edit commits, [here's a great guide](http://sethrobertson.github.io/GitFixUm/fixup.html).
9. Make sure your develop branch is up to date again and rebase onto any changes that have been made upstream since you started the branch: `git pull upstream develop --rebase`  (this command joins several steps: updating your local develop branch, and then rebasing your current feature branch on top of the updated develop branch)
10. You may need to resolve merge conflicts, if there are any. Hopefully not!  ([how to resolve a merge conflict](https://www.youtube.com/watch?v=QmKdodJU-js))
11. Push your branch to your fork of the project on github (the first time you do this, it will create the branch on github for you): `git push origin yourbranchname`
12. Go to your fork of the repository on GitHub (you should see a dropdown allowing you to select your branch)
13. Select your recently pushed branch and create a pull request (you should see a button for this)
![image](https://user-images.githubusercontent.com/10604391/125674000-d02eb7a0-b85d-4c8f-b8dd-2b144e274f7d.png)

13. Complete pull request.
14. Once automated tests have finished running on your PR, make sure they passed (they should have, since you already ran the tests locally at step 8... right? RIGHT?!)
15. Engage in the review of your pull request on github (there will likely be some back and forth discussion between you and the maintainer before the PR is accepted)
16. Start work on another feature by checking out the develop branch again: `git checkout develop`
17. Go to Step 4 and repeat!

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

## License
By contributing, you agree that your contributions will be licensed under its [GNU GPL3 License](https://github.com/timberline-secondary/hackerspace/blob/develop/license.txt).
