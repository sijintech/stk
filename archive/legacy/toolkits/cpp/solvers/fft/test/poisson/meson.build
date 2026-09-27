project_test = [
  'poisson_setup',
  'poisson_print',
  'poisson_criteria',
  'poisson_solver'
]

#   configure_file(
#     input: 'input.xml',
#     output: 'input.xml',
#     copy: true)

  foreach f : project_test
  message(f)
    test(f,
        executable(
        f,
        files(f+'.c'),
        dependencies : [project_dep,test_dep],
        install : false
        )
    ) 
  endforeach