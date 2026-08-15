// Akin to antlr/antlr4/Java/LexerAdaptor.java. 
// Since Rust has no classes 
// fields, init members and extend are specific to rust (https://github.com/rrevenantt/antlr4rust/blob/master/templates/Rust.stg)

//>>fields
current_rule_type: isize,

//>>init
current_rule_type: TOKEN_INVALID_TYPE,

//>>members
fn in_lexer_rule(&self) -> bool {
    self.current_rule_type == TOKEN_REF
}

//>>extend
fn before_emit(_lexer: &mut BaseLexer<'input, ANTLRv4LexerActions, Input, LocalTokenFactory<'input>>) {
    const PREQUEL_CONSTRUCT: isize = -10;
    const OPTIONS_CONSTRUCT: isize = -11;

    if (_lexer.token_type == OPTIONS || _lexer.token_type == TOKENS || _lexer.token_type == CHANNELS)
        && _lexer.current_rule_type == TOKEN_INVALID_TYPE
    {
        // enter prequel construct ending with an RBRACE
        _lexer.current_rule_type = PREQUEL_CONSTRUCT;
    } else if _lexer.token_type == OPTIONS && _lexer.current_rule_type == TOKEN_REF {
        _lexer.current_rule_type = OPTIONS_CONSTRUCT;
    } else if _lexer.token_type == RBRACE && _lexer.current_rule_type == PREQUEL_CONSTRUCT {
        // exit prequel construct
        _lexer.current_rule_type = TOKEN_INVALID_TYPE;
    } else if _lexer.token_type == RBRACE && _lexer.current_rule_type == OPTIONS_CONSTRUCT {
        // exit options
        _lexer.current_rule_type = TOKEN_REF;
    } else if _lexer.token_type == AT && _lexer.current_rule_type == TOKEN_INVALID_TYPE {
        // enter action
        _lexer.current_rule_type = AT;
    } else if _lexer.token_type == SEMI && _lexer.current_rule_type == OPTIONS_CONSTRUCT {
        // ';' in options { .... }. Don't change anything.
    } else if _lexer.token_type == ACTION && _lexer.current_rule_type == AT {
        // exit action
        _lexer.current_rule_type = TOKEN_INVALID_TYPE;
    } else if _lexer.token_type == ID {
        let first_upper = _lexer
            .input
            .as_ref()
            .unwrap()
            .get_text(_lexer.token_start_char_index, _lexer.token_start_char_index)
            .chars()
            .next()
            .map(|c| c.is_uppercase())
            .unwrap_or(false);
        _lexer.token_type = if first_upper { TOKEN_REF } else { RULE_REF };

        if _lexer.current_rule_type == TOKEN_INVALID_TYPE {
            // if outside of rule def, set to inside lexer or parser rule
            _lexer.current_rule_type = _lexer.token_type;
        }
    } else if _lexer.token_type == SEMI {
        // exit rule def
        _lexer.current_rule_type = TOKEN_INVALID_TYPE;
    }
}
