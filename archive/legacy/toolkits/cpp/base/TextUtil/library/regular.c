#include <ntextutils/ntextutils.h>
#define MAX_ERROR_MSG 0x1000

int n_regex_compile(regex_t * r, const char * regex_text)
{
    int status = regcomp (r, regex_text, REG_EXTENDED|REG_NEWLINE);
    if (status != 0) {
	char error_message[MAX_ERROR_MSG];
	regerror (status, r, error_message, MAX_ERROR_MSG);
        printf ("Regex error compiling '%s': %s\n",
                 regex_text, error_message);
        return 1;
    }
    return 0;
}

regmatch_t n_regex_match_nth_ngroup (char *matched, regex_t * r, const char * to_match, int nth, int ngroup)
{
    /* "P" is a pointer into the string which points to the end of the
       previous match. */
    const char * p = to_match;
    /* "N_matches" is the maximum number of matches allowed. */
    const int n_matches = ngroup+1;
    /* "M" contains the matches found. */
    regmatch_t m[n_matches];
    int length=0;
    int start=0;
    int finish=0;
    int count=0;
    while (1) {
        int i = 0;
        int nomatch = regexec (r, p, n_matches, m, 0);
        if (nomatch || count == nth) {
            printf ("No more matches.\n");
            length = (int)(finish - start);
            strncpy(matched,to_match + start, length);
            matched[length] = '\0';
            return m[ngroup];
        }
        for (i = 0; i < n_matches; i++) {

            if (m[i].rm_so == -1) {
                break;
            }
            start = m[i].rm_so + (p - to_match);
            finish = m[i].rm_eo + (p - to_match);
            if (i == 0) {
                printf ("$& is ");
            }
            else {
                printf ("$%d is ", i);
            }
            printf ("'%.*s' (bytes %d:%d)\n", (finish - start),
                    to_match + start, start, finish);
        }
        p += m[0].rm_eo;
        count++;
    }
}