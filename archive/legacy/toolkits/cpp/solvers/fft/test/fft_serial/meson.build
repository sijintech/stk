  project_test_c = ['fftw_r2c_3d']

  foreach f : project_test_c
  message(f)
    test(f,
        executable(
        f,
        files(f+'.c'),
        dependencies : [project_dep, test_dep],
        install : false
        )
    ) 
  endforeach