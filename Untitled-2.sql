DROP USER IF EXISTS 'student_finance_user'@'localhost';

CREATE USER 'student_finance_user'@'localhost'
    IDENTIFIED BY 'YERLI_PAROLU_BURAYA_YAZIN';

GRANT ALL PRIVILEGES ON student_finance.*
    TO 'student_finance_user'@'localhost';

DROP USER IF EXISTS 'student_finance_user'@'127.0.0.1';