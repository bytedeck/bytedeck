import re
import argparse


def convert_issue_hashes_to_links(file_path):
    # Read the content of the markdown file
    with open(file_path, encoding='utf-8') as file:
        content = file.read()

    # Define the pattern for GitHub issue hashes and the pattern to ignore existing links
    issue_pattern = re.compile(r'(?<!\]\()(?<!\[)\#(\d+)')

    # Replace issue hashes with the appropriate link format
    converted_content = issue_pattern.sub(r'[#\1](https://github.com/bytedeck/bytedeck/issues/\1)', content)

    # Write the converted content back to the file
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(converted_content)

    print(f"Issue hashes in '{file_path}' have been successfully converted to links.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert GitHub issue hashes to links in a markdown file.')
    parser.add_argument('file', nargs='?', default='CHANGELOG.md', help='Path to the markdown file (default: CHANGELOG.md)')

    args = parser.parse_args()
    convert_issue_hashes_to_links(args.file)
