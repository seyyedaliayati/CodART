from gen.javaLabeled.JavaLexer import JavaLexer

try:
    import understand as und
except ImportError as e:
    print(e)

from antlr4 import *
from antlr4.TokenStreamRewriter import TokenStreamRewriter

from gen.javaLabeled.JavaParserLabeled import JavaParserLabeled
from gen.javaLabeled.JavaParserLabeledListener import JavaParserLabeledListener


class CheckOverrideListener(JavaParserLabeledListener):
    pass

class PullUpMethodRefactoringListener(JavaParserLabeledListener):
    """
    To implement extract class refactoring based on its actors.
    Creates a new class and move fields and methods from the old class to the new one
    """

    def __init__(self, common_token_stream: CommonTokenStream = None, destination_class: str = None,
                 children_class: list = None, moved_methods=None, method_text: str = None):

        if method_text is None:
            self.mothod_text = []
        else:
            self.method_text = method_text

        if moved_methods is None:
            self.moved_methods = []
        else:
            self.moved_methods = moved_methods
        if children_class is None:
            self.children_class = []
        else:
            self.children_class = children_class
        if common_token_stream is None:
            raise ValueError('common_token_stream is None')
        else:
            self.token_stream_rewriter = TokenStreamRewriter(common_token_stream)

        if destination_class is None:
            raise ValueError("source_class is None")
        else:
            self.destination_class = destination_class

        self.is_children_class = False
        self.detected_field = None
        self.detected_method = None
        self.TAB = "\t"
        self.NEW_LINE = "\n"
        self.code = ""
        self.tempdeclarationcode = ""

    def enterMethodDeclaration(self, ctx: JavaParserLabeled.MethodDeclarationContext):

        if self.is_children_class:

            method_identifier = ctx.IDENTIFIER().getText()
            if self.moved_methods == method_identifier:
                methodDefctx = ctx.parentCtx.parentCtx
                start_index = methodDefctx.start.tokenIndex
                stop_index = methodDefctx.stop.tokenIndex
                self.method_text = self.token_stream_rewriter.getText(
                    program_name=self.token_stream_rewriter.DEFAULT_PROGRAM_NAME,
                    start=start_index,
                    stop=stop_index)

                self.token_stream_rewriter.delete(
                    program_name=self.token_stream_rewriter.DEFAULT_PROGRAM_NAME,
                    from_idx=methodDefctx.start.tokenIndex,
                    to_idx=methodDefctx.stop.tokenIndex
                )
        else:
            return None

    def enterClassDeclaration(self, ctx: JavaParserLabeled.ClassDeclarationContext):
        class_identifier = ctx.IDENTIFIER().getText()
        if class_identifier in self.children_class:
            self.is_children_class = True

        else:
            print("enter other class")
            self.is_children_class = False

    def enterClassBody(self, ctx: JavaParserLabeled.ClassBodyContext):
        classDecctx = ctx.parentCtx
        class_identifier = classDecctx.IDENTIFIER().getText()
        if class_identifier in self.destination_class:
            self.token_stream_rewriter.replaceRange(
                from_idx=ctx.start.tokenIndex + 1,
                to_idx=ctx.start.tokenIndex + 1,
                text="\n" + self.method_text + "\n"
            )

    def exitClassDeclaration(self, ctx: JavaParserLabeled.ClassDeclarationContext):
        if self.is_children_class:
            self.is_children_class = False

    def exitCompilationUnit(self, ctx: JavaParserLabeled.CompilationUnitContext):

        self.token_stream_rewriter.insertAfter(
            index=ctx.stop.tokenIndex,
            text=self.code
        )


class PropagationPullUpMethodRefactoringListener(JavaParserLabeledListener):

    def __init__(self, token_stream_rewriter: CommonTokenStream = None, old_class_name: list = None,
                 new_class_name: str = None, propagated_class_name: list = None):

        if propagated_class_name is None:
            self.propagated_class_name = []
        else:
            self.propagated_class_name = propagated_class_name

        if new_class_name is None:
            self.new_class_name = []
        else:
            self.new_class_name = new_class_name

        if old_class_name is None:
            self.old_class_name = []
        else:
            self.old_class_name = old_class_name

        if token_stream_rewriter is None:
            raise ValueError('token_stream_rewriter is None')
        else:
            self.token_stream_rewriter = TokenStreamRewriter(token_stream_rewriter)

        self.is_class = False
        self.detected_field = None
        self.detected_method = None
        self.TAB = "\t"
        self.NEW_LINE = "\n"
        self.code = ""
        self.tempdeclarationcode = ""
        self.method_text = ""

    def enterVariableDeclarator(self, ctx: JavaParserLabeled.VariableDeclaratorContext):
        print("Propagation started, please wait...")
        if not self.is_class:
            return None
        grand_parent_ctx = ctx.parentCtx.parentCtx
        class_identifier = grand_parent_ctx.typeType().getText()
        if class_identifier in self.old_class_name:
            self.token_stream_rewriter.replaceRange(
                from_idx=grand_parent_ctx.typeType().start.tokenIndex,
                to_idx=grand_parent_ctx.typeType().stop.tokenIndex,
                text=self.new_class_name
            )
            grand_child_ctx = ctx.variableInitializer().expression().creator().createdName()
            self.token_stream_rewriter.replaceRange(
                from_idx=grand_child_ctx.start.tokenIndex,
                to_idx=grand_child_ctx.stop.tokenIndex,
                text=self.new_class_name
            )

    def enterClassDeclaration(self, ctx: JavaParserLabeled.ClassDeclarationContext):
        class_identifier = ctx.IDENTIFIER().getText()
        if class_identifier in self.propagated_class_name:
            self.is_class = True

        else:
            print("enter other class")
            self.is_class = False


def main(udb_path: str, children_classes: list, method_name: str):
    if len(children_classes) <= 1:
        print("len(children_classes) should be gte 2")
        return None

    # initialize with understand
    destination_class = ""
    fileslist_to_be_rafeactored = set()
    fileslist_to_be_propagate = set()
    propagation_classes = set()
    db = und.open(udb_path)
    try:
        method_ents = [db.lookup(i + "." + method_name, "method")[0] for i in children_classes]
    except IndexError:
        print([db.lookup(i + "." + method_name, "method") for i in children_classes])
        print(f"Method {method_name} does not exists in all children_classes.")
        return None

    # Get method text
    method_text = method_ents[0].contents().strip()
    print("method_text:", method_text)
    # end get text

    for method_ent in method_ents:
        if method_ent.contents().strip() != method_text:
            print("Method content is different.")
            return None

        for ref in method_ent.refs("Use,Call"):
            if ref.ent().parent().simplename() in children_classes:
                print("Method has internal dependencies.")
                return None

    for mth in db.ents("Java Method"):
        for child in children_classes:
            if mth.longname().endswith(child + "." + method_name):
                fileslist_to_be_rafeactored.add(mth.parent().parent().longname())
                for fth in mth.parent().refs("Extend"):
                    destination_class = fth.ent().longname()
                    fileslist_to_be_rafeactored.add(fth.ent().parent().longname())
                for ref in mth.refs("Java Callby"):
                    propagation_classes.add(ref.ent().parent().longname())
                    fileslist_to_be_propagate.add(ref.ent().parent().parent().longname())
    print("=========================================")
    print("fileslist_to_be_propagate :", fileslist_to_be_propagate)
    print("propagation_classes : ", propagation_classes)
    print("fileslist_to_be_rafeactored :", fileslist_to_be_rafeactored)
    print("father class :", destination_class)

    fileslist_to_be_rafeactored = list(fileslist_to_be_rafeactored)
    fileslist_to_be_propagate = list(fileslist_to_be_propagate)
    propagation_class = list(propagation_classes)

    # refactored start
    for file in fileslist_to_be_rafeactored:
        stream = FileStream(file, encoding='utf8')
        lexer = JavaLexer(stream)
        token_stream = CommonTokenStream(lexer)
        parser = JavaParserLabeled(token_stream)
        parser.getTokenStream()
        parse_tree = parser.compilationUnit()
        my_listener_refactor = PullUpMethodRefactoringListener(common_token_stream=token_stream,
                                                               destination_class=destination_class,
                                                               children_class=children_classes,
                                                               moved_methods=method_name,
                                                               method_text=method_text)
        walker = ParseTreeWalker()
        walker.walk(t=parse_tree, listener=my_listener_refactor)

        with open(file, mode='w', newline='') as f:
            f.write(my_listener_refactor.token_stream_rewriter.getDefaultText())
    # end refactoring

    # beginning of propagate
    for file in fileslist_to_be_propagate:
        stream = FileStream(file, encoding='utf8')
        lexer = JavaLexer(stream)
        token_stream = CommonTokenStream(lexer)
        parser = JavaParserLabeled(token_stream)
        parser.getTokenStream()
        parse_tree = parser.compilationUnit()
        my_listener_propagate = PropagationPullUpMethodRefactoringListener(token_stream_rewriter=token_stream,
                                                                           old_class_name=children_classes,
                                                                           new_class_name=destination_class,
                                                                           propagated_class_name=propagation_class)
        walker = ParseTreeWalker()
        walker.walk(t=parse_tree, listener=my_listener_propagate)

        with open(file, mode='w', newline='') as f:
            f.write(my_listener_propagate.token_stream_rewriter.getDefaultText())
    # end of propagate


if __name__ == '__main__':
    udb_path = "D:\Dev\JavaSample\JavaSample1.udb"
    children_class = ["Tank", "Soldier"]
    moved_method = "getHealth"
    main(
        udb_path=udb_path,
        children_classes=children_class,
        method_name=moved_method
    )

