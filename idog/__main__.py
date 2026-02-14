import sys

from .encoder import KGPEncoderBase
from .unicode import KGPEncoderUnicode
from .query import KGPQuery
from .cli_options import KGPOptions


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    options = KGPOptions(KGPOptions.get_parser().parse_args(args=args))

    if options.do_query:
        for k, v in KGPQuery.query().items():
            print(f"{k}: {v}")
        return

    encoder = None
    sequences = []
    placeholders = []
    if options.unicode_placeholder == 1:
        encoder = KGPEncoderUnicode(options)
        sequences = encoder.construct_KGP()
        placeholders = encoder.construct_unicode_placeholders()
    else:
        encoder = KGPEncoderBase(options)
        sequences = encoder.construct_KGP()

    for seq in sequences:
        print(seq, end="")

    # placeholders is only used when Unicode Placeholder is enabled,
    # and will be empty otherwise, so this loop will be skipped when not needed
    for i, line in enumerate(placeholders):
        # Only print a newline after each line except the last one
        print(line, end="" if i == len(placeholders) - 1 else "\n")

    # Final new line
    print("")

    # Delete image on user input
    # input()
    # print(encoder.delete_image())


if __name__ == "__main__":
    main()
