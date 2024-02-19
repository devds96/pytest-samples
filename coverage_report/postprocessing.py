"""Executing this script will print the coverage information to stdout
and write the SVG image of the coverage badge to a file.
"""

import coverage
import pybadges
import sys
import traceback
import xml.dom.minidom as minidom

from argparse import ArgumentParser
from typing import Dict, Optional


BADGE_TEXT = "coverage"
"""The right hand side text for the badge."""


BADGE_TITLE = "coverage - {text}"
"""The title for the badge image."""


FAILING_TEXT = "failing"
"""The text when no coverage can be calculated."""


PERCENTAGE_TEXT = "{value:.2f}%"
"""The text for the right hand side coverage percentage text."""


XML_INDENT = ' ' * 4
"""The amount of indentation for the final badge SVG."""


def setup_argparse() -> ArgumentParser:
    """Set up the argument parser.

    Returns:
        ArgumentParser: The argument parser for this script.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "config_file",
        help="The path to the config file for the coverage report."
    )
    parser.add_argument(
        "output_file",
        help="The file to which to write the badge SVG data."
    )
    parser.add_argument(
        "link",
        help="The link to open when the image is clicked."
    )
    parser.add_argument(
        "--data-file", metavar="data_file",
        help=(
            "The data file from which to read the coverage data. "
            "Defaults to the default specified by the coverage package."
        )
    )
    return parser


def get_badge_color(cov: Optional[float]) -> str:
    """Compute the color of the coverage badge.

    Args:
        cov (float | None): The total coverage or None, if an error
            occurred.

    Returns:
        str: The color to use for the badge's right hand side.
    """
    if cov is None:
        return "#828282"
    if cov >= 98:
        return "#3CCE35"
    elif cov >= 90:
        return "#b9ef20"
    elif cov >= 60:
        return "#ff7000"
    return "ff0000"


def make_badge_svg(cov: Optional[float], link: str) -> str:
    """Create the badge SVG string.

    Args:
        cov (float | None): The coverage.

    Returns:
        str: The badge as an SVG string
    """
    if cov is None:
        text = FAILING_TEXT
        wlink = None
    else:
        text = PERCENTAGE_TEXT.format(value=cov)
        wlink = link
    color = get_badge_color(cov)
    title = BADGE_TITLE.format(text=text)
    badge_svg_str = pybadges.badge(
        BADGE_TEXT, text, right_color=color, whole_link=wlink,
        whole_title=title
    )
    return prettify_svg_str(badge_svg_str)


def prettify_svg_str(svg: str, *, indent: Optional[str] = None) -> str:
    """Prettifies an SVG str.

    Args:
        svg (str): The str to process.
        indent (str, optional): The indentation to use. Defaults to
            `XML_INDENT`.

    Returns:
        str: The prettified SVG.
    """
    svg_badge_dom = minidom.parseString(svg)
    # The document itself starts with the xml header which we do not
    # need for an SVG image. Therefore, use the documentElement instead.
    svg_badge_de: minidom.Element = svg_badge_dom.documentElement
    if indent is None:
        indent = XML_INDENT
    pretty_svg = svg_badge_de.toprettyxml(indent=indent)
    return pretty_svg


def main() -> None:
    """The main function for this script."""
    arg_parser = setup_argparse()
    args = arg_parser.parse_args()

    kw: Dict[str, object] = dict()
    df_arg = args.data_file
    if df_arg is not None:
        kw["data_file"] = args.data_file

    try:
        cov = coverage.Coverage(
            **kw,  # type: ignore
            config_file=args.config_file
        )
        cov.load()
        # This will also print the coverage report to stdout.
        total_coverage = cov.report(show_missing=True)
    except Exception:
        traceback.print_exc()
        print("Setting coverage to None.", file=sys.stderr)
        total_coverage = None
    else:
        print("total coverage:", f"{total_coverage:.2f}%", file=sys.stderr)

    badge_svg = make_badge_svg(total_coverage, args.link)
    with open(args.output_file, 'w') as ofi:
        ofi.write(badge_svg)


if __name__ == "__main__":
    main()
