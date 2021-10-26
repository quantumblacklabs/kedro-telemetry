# Copyright 2021 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
# or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module containing command masking functionality."""

from typing import Any, Dict, Iterator, List, Set, Tuple, Union

import click


def _recurse_cli(
    cli_element: Union[click.Command, click.Group, click.CommandCollection],
    ctx: click.Context,
    io_dict: Dict[str, Any],
    get_help: bool = False,
) -> None:
    """
    Code copied over from kedro.tools.cli to maintain backwards compatibility
    with previous versions of kedro (<0.17.5).

    Recursive function that checks the type of the command (key) and decides:
    1. In case of `click.Group` or `click.CommandCollection` (aggregate commands),
        the function collects the name and recurses one layer deeper
        for each sub-command.
    2. In case of `click.Command`, the terminus command has been reached. The function
        collects the name, parameters and args, flattens them and saves them as
        dictionary keys.
    Args:
        cli_element: CLI Collection as input for recursion, typically `KedroCLI`.
        ctx: Click Context, created by the wrapper function.
        io_dict: Input-output dictionary, mutated during the recursion.
        get_help: Boolean fork - allows either:
            raw structure - nested dictionary until final value of `None`
            help structure - nested dictionary where leaves are `--help` cmd output

    Returns:
        None (underlying `io_dict` is mutated by the recursion)
    """
    if isinstance(cli_element, (click.Group, click.CommandCollection)):
        element_name = cli_element.name or "kedro"
        io_dict[element_name] = {}
        for _sc in cli_element.list_commands(ctx):
            _recurse_cli(  # type: ignore
                cli_element.get_command(ctx, _sc), ctx, io_dict[element_name], get_help,
            )

    elif isinstance(cli_element, click.Command):
        if get_help:  # gets formatted CLI help incl params for printing
            io_dict[cli_element.name] = cli_element.get_help(ctx)
        else:  # gets params for structure purposes
            l_of_l = [_o.opts for _o in cli_element.get_params(ctx)]
            io_dict[cli_element.name] = dict.fromkeys(
                [item for sublist in l_of_l for item in sublist], None
            )


def get_cli_structure(
    cli_obj: Union[click.Command, click.Group, click.CommandCollection],
    get_help: bool = False,
) -> Dict[str, Any]:
    """Code copied over from kedro.tools.cli to maintain backwards compatibility
    with previous versions of kedro (<0.17.5).
    Convenience wrapper function for `_recurse_cli` to work within
    `click.Context` and return a `dict`.
    """
    output: Dict[str, Any] = {}
    with click.Context(cli_obj) as ctx:  # type: ignore
        _recurse_cli(cli_obj, ctx, output, get_help)
    return output


def mask_kedro_cli(cli_struct: Dict[str, Any], command_args: List[str]) -> List[str]:
    """Takes a dynamic vocabulary (based on `KedroCLI`) and returns
    a masked CLI input"""
    output = []
    mask = "*****"
    vocabulary = _get_vocabulary(cli_struct)
    for arg in command_args:
        if arg.startswith("-"):
            for arg_part in arg.split("="):
                if arg_part in vocabulary:
                    output.append(arg_part)
                elif arg_part:
                    output.append(mask)
        else:
            if arg in vocabulary:
                output.append(arg)
            elif arg:
                output.append(mask)
    return output


def _get_vocabulary(cli_struct: Dict[str, Any]) -> Set[str]:
    """Builds a unique whitelist of terms - a vocabulary"""
    vocabulary = {"-h", "--version"}  # -h help and version args are not in by default
    for _k, _v in _recursive_items(cli_struct):
        vocabulary.add(_k)
        if _v:
            vocabulary.add(_v)
    return vocabulary


def _recursive_items(dictionary: Dict[Any, Any]) -> Iterator[Tuple[str, Any]]:
    for key, value in dictionary.items():
        if isinstance(value, dict):
            yield key, None
            yield from _recursive_items(value)
        else:
            yield key, value
